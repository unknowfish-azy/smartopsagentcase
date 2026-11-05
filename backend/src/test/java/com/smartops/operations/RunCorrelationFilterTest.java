package com.smartops.operations;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class RunCorrelationFilterTest {
    @Test void preservesValidHeadersAndOnlyIdsInMdcThenClears() throws Exception {
        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();
        request.addHeader("X-Request-ID", "req_1:ok"); request.addHeader("X-Task-ID", "task.2"); request.addHeader("X-Run-ID", "run-3");
        request.addHeader("Authorization", "Bearer secret");
        new RunCorrelationFilter().doFilter(request, response, (req, res) -> {
            assertEquals(Map.of("request_id", "req_1:ok", "task_id", "task.2", "run_id", "run-3"), MDC.getCopyOfContextMap());
            assertEquals("req_1:ok", req.getAttribute("request_id"));
            assertEquals("1.0.0", req.getAttribute("run_event_schema_version"));
        });
        assertEquals("req_1:ok", response.getHeader("X-Request-ID"));
        assertEquals("task.2", response.getHeader("X-Task-ID"));
        assertEquals("run-3", response.getHeader("X-Run-ID"));
        assertTrue(MDC.getCopyOfContextMap() == null || MDC.getCopyOfContextMap().isEmpty());
    }
    @Test void invalidMissingNewlineAndLongIdsAreReplaced() throws Exception {
        for (String invalid : new String[]{"", "bad\nHeader", "a".repeat(97), "_bad", "中文", " space"}) {
            var request = new MockHttpServletRequest(); var response = new MockHttpServletResponse();
            for (String header : new String[]{"X-Request-ID", "X-Task-ID", "X-Run-ID"}) request.addHeader(header, invalid);
            new RunCorrelationFilter().doFilter(request, response, (req, res) -> {});
            for (String header : new String[]{"X-Request-ID", "X-Task-ID", "X-Run-ID"}) {
                String actual = response.getHeader(header);
                assertNotEquals(invalid, actual); assertTrue(actual.matches("[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}"));
            }
        }
        var response = new MockHttpServletResponse();
        new RunCorrelationFilter().doFilter(new MockHttpServletRequest(), response, (req, res) -> {});
        assertEquals(response.getHeader("X-Request-ID"), response.getHeader("X-Task-ID"));
    }
    @Test void exceptionAlsoClearsMdc() {
        assertThrows(jakarta.servlet.ServletException.class, () -> new RunCorrelationFilter().doFilter(new MockHttpServletRequest(), new MockHttpServletResponse(), (req, res) -> { throw new jakarta.servlet.ServletException("failure"); }));
        assertTrue(MDC.getCopyOfContextMap() == null || MDC.getCopyOfContextMap().isEmpty());
    }
    @RestController static class Echo {
        @GetMapping("/correlation-test") Map<String, String> echo(jakarta.servlet.http.HttpServletRequest request) {
            return Map.of("request_id", request.getAttribute("request_id").toString(), "run_id", MDC.get("run_id"));
        }
    }
    @Test void mockMvcBoundaryReturnsSameIdsToCaller() throws Exception {
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new Echo()).addFilters(new RunCorrelationFilter()).build();
        mvc.perform(get("/correlation-test").header("X-Request-ID", "request-1").header("X-Run-ID", "run-1"))
            .andExpect(status().isOk()).andExpect(header().string("X-Request-ID", "request-1"))
            .andExpect(header().string("X-Run-ID", "run-1")).andExpect(jsonPath("$.request_id").value("request-1"))
            .andExpect(jsonPath("$.run_id").value("run-1"));
    }
}
