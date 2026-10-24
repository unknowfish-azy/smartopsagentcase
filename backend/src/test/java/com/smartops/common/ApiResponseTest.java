package com.smartops.common;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ApiResponseTest {

    @Test
    void successShouldReturnCorrectResult() {

        ApiResponse<String> response =
                ApiResponse.success("test");

        assertEquals(200, response.getCode());
        assertEquals("success", response.getMessage());
        assertEquals("test", response.getData());
    }

    @Test
    void successWithoutDataShouldReturnNullData() {

        ApiResponse<Void> response =
                ApiResponse.success();

        assertEquals(200, response.getCode());
        assertEquals("success", response.getMessage());
        assertNull(response.getData());
    }

    @Test
    void errorShouldReturnCorrectResult() {

        ApiResponse<Void> response =
                ApiResponse.error(400, "参数错误");

        assertEquals(400, response.getCode());
        assertEquals("参数错误", response.getMessage());
        assertNull(response.getData());
    }
}