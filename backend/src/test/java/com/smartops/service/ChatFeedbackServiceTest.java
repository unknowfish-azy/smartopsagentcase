package com.smartops.service;

import com.smartops.assistant.MiniAssistantEngine;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** 复核结论三态判定：全部基于真实引用与明确措辞，不靠猜测。 */
class ChatFeedbackServiceTest {
    private static MiniAssistantEngine.Reply reply(String content, MiniAssistantEngine.Evidence... evidence) {
        return new MiniAssistantEngine.Reply(content, "test-model", List.of(evidence), Map.of());
    }
    private static MiniAssistantEngine.Evidence evidence() {
        return new MiniAssistantEngine.Evidence("k1", "运维知识", "personal", "证据片段");
    }

    @Test
    void noRealCitationIsNeverConfirmed() {
        assertEquals(ChatFeedbackService.UNCONFIRMED,
                ChatFeedbackService.decideConclusion(reply("我推测应该这样改")));
        assertEquals(ChatFeedbackService.UNCONFIRMED,
                ChatFeedbackService.decideConclusion(reply("这是修正答案")));
    }

    @Test
    void explicitUncertainWordingIsUnconfirmedEvenWithCitations() {
        assertEquals(ChatFeedbackService.UNCONFIRMED,
                ChatFeedbackService.decideConclusion(reply("证据不足，无法确认该问题", evidence())));
    }

    @Test
    void explicitOriginalOkIsNotPublishedAsCorrection() {
        assertEquals(ChatFeedbackService.ORIGINAL_OK,
                ChatFeedbackService.decideConclusion(reply("原答案正确，引用支持原结论", evidence())));
    }

    @Test
    void confirmedRequiresCitationAndDefinitiveAnswer() {
        assertEquals(ChatFeedbackService.CONFIRMED,
                ChatFeedbackService.decideConclusion(reply("原答案有误，正确结论是 X", evidence())));
    }
}
