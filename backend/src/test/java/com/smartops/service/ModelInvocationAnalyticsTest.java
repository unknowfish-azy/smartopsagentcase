package com.smartops.service;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.dto.model.ModelInvocationRequest;
import com.smartops.dto.model.ModelInvocationResponse;
import com.smartops.entity.ModelConnection;
import com.smartops.mapper.ModelConnectionMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ModelInvocationAnalyticsTest {
    @Test void missingOrOtherUsersConnectionIsNotFoundWithoutInvokingProvider() {
        assertThatThrownBy(() -> service.invoke(99L, 2L, request))
                .isInstanceOfSatisfying(com.smartops.exception.BusinessException.class, error -> assertThat(error.getCode()).isEqualTo(404));
        verify(mapper).findById(2L, 99L);
        verifyNoInteractions(provider, analytics, crypto);
    }
    private final ModelConnectionMapper mapper = mock(ModelConnectionMapper.class);
    private final AesGcmCryptoService crypto = mock(AesGcmCryptoService.class);
    private final ModelProviderClient provider = mock(ModelProviderClient.class);
    private final ModelAnalyticsService analytics = mock(ModelAnalyticsService.class);
    private final ModelConnectionService service = new ModelConnectionService(mapper, crypto, provider, analytics);
    private ModelConnection connection;
    private final ModelInvocationRequest request = new ModelInvocationRequest();
    @BeforeEach void setup() {
        connection = new ModelConnection(); connection.setEnabled(true); connection.setModelName("model-a"); connection.setApiKeyCiphertext("encrypted");
        connection.setBaseUrl("http://8.8.8.8/v1");
        when(mapper.findById(2L, 7L)).thenReturn(connection);
        when(crypto.decrypt("encrypted")).thenReturn("secret");
        when(analytics.start(7L, 2L, "model-a")).thenReturn("invocation");
    }
    @Test void recordsSuccessAndUsageAfterStartingLedger() {
        var response = ModelInvocationResponse.builder().content("answer").usage(Map.of("total_tokens", 4)).build();
        when(provider.invoke(connection, "secret", request)).thenReturn(response);
        assertThat(service.invoke(7L, 2L, request)).isSameAs(response);
        var order = inOrder(analytics, provider);
        order.verify(analytics).start(7L, 2L, "model-a");
        order.verify(provider).invoke(connection, "secret", request);
        order.verify(analytics).finish(eq("invocation"), eq(true), anyLong(), eq(response.getUsage()));
    }
    @Test void verifiedAddressIsPinnedForOutboundAndClearedAfterward() {
        var pinnedDuringCall = new java.util.concurrent.atomic.AtomicBoolean();
        var response = ModelInvocationResponse.builder().content("answer").usage(Map.of()).build();
        when(provider.invoke(connection, "secret", request)).thenAnswer(invocation -> {
            pinnedDuringCall.set(com.smartops.security.PinnedDns.isPinned("8.8.8.8"));
            return response;
        });
        assertThat(service.invoke(7L, 2L, request)).isSameAs(response);
        assertThat(pinnedDuringCall).isTrue();
        assertThat(com.smartops.security.PinnedDns.isPinned("8.8.8.8")).isFalse();
    }
    @Test void recordsFailureAndRetainsProviderException() {
        var failure = new IllegalStateException("provider unavailable");
        when(provider.invoke(connection, "secret", request)).thenThrow(failure);
        assertThatThrownBy(() -> service.invoke(7L, 2L, request)).isSameAs(failure);
        verify(analytics).finish(eq("invocation"), eq(false), anyLong(), eq(Map.of()));
    }
    @Test void emptyResponsesAreFailedButTheirUsageIsRetained() {
        when(provider.invoke(connection, "secret", request)).thenReturn(ModelInvocationResponse.builder().content("").usage(Map.of("total_tokens", 4)).build());
        service.invoke(7L, 2L, request);
        verify(analytics).finish(eq("invocation"), eq(false), anyLong(), eq(Map.of("total_tokens", 4)));
    }
    @Test void finalizationOutageDoesNotCausePaidSuccessToBeRetried() {
        var response = ModelInvocationResponse.builder().content("answer").usage(Map.of()).build();
        when(provider.invoke(connection, "secret", request)).thenReturn(response);
        doThrow(new IllegalStateException("db down")).when(analytics).finish(anyString(), anyBoolean(), anyLong(), anyMap());
        assertThat(service.invoke(7L, 2L, request)).isSameAs(response);
    }
    @Test void disabledOrUnrecordableCallsNeverReachProvider() {
        connection.setEnabled(false);
        assertThatThrownBy(() -> service.invoke(7L, 2L, request)).isInstanceOf(IllegalStateException.class);
        verifyNoInteractions(provider, analytics);
        connection.setEnabled(true);
        when(analytics.start(7L, 2L, "model-a")).thenThrow(new IllegalStateException("db down"));
        assertThatThrownBy(() -> service.invoke(7L, 2L, request)).isInstanceOf(IllegalStateException.class);
        verifyNoInteractions(provider);
    }
}
