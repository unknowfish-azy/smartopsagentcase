package com.smartops.controller;

import com.smartops.exception.GlobalExceptionHandler;
import com.smartops.security.CurrentUserArgumentResolver;
import com.smartops.security.SessionUser;
import com.smartops.service.ModelAnalyticsService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ModelAnalyticsControllerTest {
    private ModelAnalyticsService service;
    private MockMvc mvc;
    @BeforeEach void setup() {
        service = mock(ModelAnalyticsService.class);
        mvc = MockMvcBuilders.standaloneSetup(new ModelAnalyticsController(service))
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new CurrentUserArgumentResolver())
                .build();
    }
    private static UsernamePasswordAuthenticationToken auth(long id) {
        return UsernamePasswordAuthenticationToken.authenticated(
                new SessionUser(id, "u", "user"), null, List.of());
    }
    @Test void readsOwnedMonthAndOptionalConnection() throws Exception {
        when(service.report(7L, YearMonth.of(2026, 9), 2L)).thenReturn(Map.of("month", "2026-09"));
        mvc.perform(get("/api/model-analytics")
                        .principal(auth(7L))
                        .param("month", "2026-09").param("connectionId", "2"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.month").value("2026-09"));
        verify(service).report(7L, YearMonth.of(2026, 9), 2L);
    }
    @Test void rejectsInvalidMonthsAndFractionalOrOutOfRangeBudgets() throws Exception {
        for (String month : new String[]{"2026-13", "1999-12", "2101-01", "2026-9"}) {
            mvc.perform(get("/api/model-analytics")
                            .principal(auth(1L))
                            .param("month", month)).andExpect(jsonPath("$.code").value(400));
        }
        for (String limit : new String[]{"1.5", "-1", "1000000000001", "999999999999999999999999"}) {
            mvc.perform(put("/api/model-analytics/budget")
                            .principal(auth(1L))
                            .contentType("application/json")
                            .content("{\"month\":\"2026-09\",\"tokenLimit\":" + limit + "}"))
                    .andExpect(jsonPath("$.code").value(400));
        }
        verifyNoInteractions(service);
    }
    @Test void acceptsZeroAndNullWithoutCoercion() throws Exception {
        for (String limit : new String[]{"0", "null"}) {
            mvc.perform(put("/api/model-analytics/budget")
                            .principal(auth(8L))
                            .contentType("application/json")
                            .content("{\"month\":\"2026-09\",\"tokenLimit\":" + limit + "}"))
                    .andExpect(status().isOk());
        }
        verify(service).saveBudget(8L, YearMonth.of(2026, 9), 0L);
        verify(service).saveBudget(8L, YearMonth.of(2026, 9), null);
    }
}
