package com.smartops.study;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-17：课程目录可读、知识点按章节分组、掌握度按用户隔离且可重置。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:study_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class StudyServiceIntegrationTest {

    private static final long OWNER = 151L;
    private static final long OTHER = 152L;

    @Autowired JdbcTemplate jdbc;
    @Autowired StudyService study;

    /** 进度表跨测试共享（DB_CLOSE_DELAY=-1），用例间必须清空，避免掌握度串味。 */
    @BeforeEach
    void cleanProgress() {
        jdbc.update("DELETE FROM study_point_progress");
    }

    @Test
    @DisplayName("总览包含全部课程，并按分类聚合统计知识点与掌握数")
    void overviewAggregatesCatalog() {
        StudyService.OverviewView overview = study.overview(OWNER);

        assertThat(overview.courseCount()).isGreaterThanOrEqualTo(13);
        assertThat(overview.pointCount()).isPositive();
        assertThat(overview.categories()).containsKeys("编程基础", "Java", "数据库", "网络", "AI");
        int summed = overview.categories().values().stream()
                .mapToInt(courses -> courses.stream().mapToInt(StudyService.CourseSummaryView::pointCount).sum())
                .sum();
        assertThat(summed).isEqualTo(overview.pointCount());
        assertThat(overview.masteredPercent()).isZero();
    }

    @Test
    @DisplayName("单课查询按章节分组，未登录进度时 mastered 全为 false")
    void courseGroupsPointsByChapter() {
        StudyService.CourseDetailView course = study.course(OWNER, "data-structures-c");

        assertThat(course.course().title()).isNotBlank();
        assertThat(course.chapters()).isNotEmpty();
        assertThat(course.chapters().get(0).points()).isNotEmpty();
        assertThat(course.chapters().get(0).points().get(0).body()).isNotBlank();
        assertThat(course.chapters().stream()
                .flatMap(chapter -> chapter.points().stream())
                .allMatch(point -> !point.mastered())).isTrue();
    }

    @Test
    @DisplayName("掌握度写入是幂等的，且严格按用户隔离")
    void progressIsIdempotentAndUserScoped() {
        long pointId = firstPointOf("cpp-programming");

        study.saveProgress(OWNER, new StudyController.ProgressInput(pointId, true, "注意 move 语义"));
        StudyService.PointProgressView saved = study.saveProgress(OWNER,
                new StudyController.ProgressInput(pointId, true, "更新备注"));
        assertThat(saved.mastered()).isTrue();
        assertThat(saved.note()).isEqualTo("更新备注");
        assertThat(countRows(pointId)).isEqualTo(1);

        assertThat(study.overview(OTHER).masteredCount()).isZero();

        study.saveProgress(OWNER, new StudyController.ProgressInput(pointId, false, null));
        assertThat(countRows(pointId)).isZero();
        assertThat(study.overview(OWNER).masteredCount()).isZero();
    }

    @Test
    @DisplayName("不存在的课程与知识点给出 404，清空只影响本人的进度")
    void missingCourseAndPointAreRejected() {
        assertThatThrownBy(() -> study.course(OWNER, "not-a-course"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("STUDY_COURSE_NOT_FOUND");
        assertThatThrownBy(() -> study.saveProgress(OWNER,
                new StudyController.ProgressInput(999_999_999L, true, null)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("STUDY_POINT_NOT_FOUND");

        long pointId = firstPointOf("python-programming");
        study.saveProgress(OWNER, new StudyController.ProgressInput(pointId, true, null));
        study.saveProgress(OTHER, new StudyController.ProgressInput(pointId, true, null));

        StudyService.ResetView reset = study.reset(OWNER, "python-programming");
        assertThat(reset.cleared()).isEqualTo(1);
        assertThat(countRows(pointId)).isEqualTo(1);
    }

    private long firstPointOf(String courseCode) {
        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM study_point WHERE course_code=? ORDER BY chapter_no, sort_no LIMIT 1",
                Long.class, courseCode);
        assertThat(ids).as("课程 %s 应已灌入语料", courseCode).isNotEmpty();
        return ids.get(0);
    }

    private int countRows(long pointId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM study_point_progress WHERE point_id=?", Integer.class, pointId);
        return count == null ? 0 : count;
    }
}
