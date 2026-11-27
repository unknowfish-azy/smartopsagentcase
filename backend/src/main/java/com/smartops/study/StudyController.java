package com.smartops.study;

import com.smartops.common.ApiResponse;
import com.smartops.security.CurrentUser;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.RequiredArgsConstructor;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * OPS-17：学习中心 / 课程知识库。
 *
 * <p>把教材与实验资料蒸馏成结构化「课程 → 章节 → 知识点」语料，落到数据库供前端
 * 分级浏览与个人掌握度勾选；网络实验与 AI 性能工程实验作为同一目录下的两门课接入，
 * 不另建一套体系。只读目录、写自己的进度，不引入协作或分享语义。</p>
 */
@RestController
@RequestMapping("/api/study")
@RequiredArgsConstructor
public class StudyController {

    private final StudyService service;

    /** 学习总览：课程清单 + 全局掌握度。 */
    @GetMapping("/overview")
    public ApiResponse<StudyService.OverviewView> overview(@CurrentUser Long userId) {
        return ApiResponse.success(service.overview(userId));
    }

    /** 课程卡片列表（按分类分组）。 */
    @GetMapping("/courses")
    public ApiResponse<java.util.List<StudyService.CourseSummaryView>> courses(@CurrentUser Long userId) {
        return ApiResponse.success(service.courses(userId));
    }

    /** 单门课的章节与知识点树（含当前用户的掌握状态）。 */
    @GetMapping("/courses/{code}")
    public ApiResponse<StudyService.CourseDetailView> course(@CurrentUser Long userId,
                                                             @PathVariable String code) {
        return ApiResponse.success(service.course(userId, code));
    }

    /** 勾选 / 取消某个知识点的掌握状态。 */
    @PostMapping("/progress")
    public ApiResponse<StudyService.PointProgressView> progress(
            @CurrentUser Long userId,
            @Valid @RequestBody ProgressInput input) {
        return ApiResponse.success(service.saveProgress(userId, input));
    }

    /** 清空某门课的个人进度（目录语料不动）。 */
    @PostMapping("/courses/{code}/reset")
    public ApiResponse<StudyService.ResetView> reset(@CurrentUser Long userId,
                                                     @PathVariable String code) {
        return ApiResponse.success(service.reset(userId, code));
    }

    public record ProgressInput(@NotNull(message = "STUDY_POINT_ID_REQUIRED: 缺少知识点 id") Long pointId,
                                @NotNull(message = "STUDY_MASTERED_REQUIRED: 缺少掌握标记") Boolean mastered,
                                String note) {}
}
