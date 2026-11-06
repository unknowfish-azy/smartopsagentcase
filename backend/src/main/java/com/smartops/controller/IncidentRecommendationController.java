package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.service.IncidentRecommendationService;
import com.smartops.service.OperatorMemoryService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge/recommendations")
@RequiredArgsConstructor
public class IncidentRecommendationController {
    private final IncidentRecommendationService recommendations;
    private final OperatorMemoryService memories;

    @PostMapping
    public ApiResponse<?> recommend(@CurrentUser Long userId, @RequestBody IncidentRecommendationService.IncidentPattern incident) {
        return ApiResponse.success(recommendations.recommend(incident, memories.list(userId)));
    }
}
