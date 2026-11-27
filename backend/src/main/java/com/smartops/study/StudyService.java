package com.smartops.study;

import com.smartops.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * OPS-17：学习中心的目录读取与个人掌握度写入。
 *
 * <p>目录数据由 db/migration 的语料初始化语句灌入，运行期只读；唯一可写的是
 * study_point_progress（按用户隔离）。知识点正文可能较长，因此单课查询一次性取回
 * 并在内存里按章节分组，避免前端为每个章节再打一次接口。</p>
 */
@Service
@RequiredArgsConstructor
public class StudyService {

    private final JdbcTemplate jdbc;

    /** 学习总览：课程清单 + 全局统计。 */
    public OverviewView overview(long userId) {
        List<CourseSummaryView> courses = courseRows(userId);
        int totalPoints = courses.stream().mapToInt(CourseSummaryView::pointCount).sum();
        int masteredPoints = courses.stream().mapToInt(CourseSummaryView::masteredCount).sum();
        Map<String, List<CourseSummaryView>> grouped = new LinkedHashMap<>();
        for (CourseSummaryView course : courses) {
            grouped.computeIfAbsent(course.category(), ignored -> new ArrayList<>()).add(course);
        }
        double percent = totalPoints == 0 ? 0 : Math.round(1000.0 * masteredPoints / totalPoints) / 10.0;
        return new OverviewView(percent, courses.size(), totalPoints, masteredPoints, grouped);
    }

    /** 课程卡片列表。 */
    public List<CourseSummaryView> courses(long userId) {
        return courseRows(userId);
    }

    /** 单门课的章节树。 */
    public CourseDetailView course(long userId, String code) {
        CourseSummaryView meta = courseRows(userId).stream()
                .filter(course -> course.code().equals(code))
                .findFirst()
                .orElseThrow(() -> new BusinessException(404, "STUDY_COURSE_NOT_FOUND: 课程不存在: " + code));

        List<PointView> points = jdbc.query("""
                SELECT p.id, p.chapter_no, p.chapter_title, p.point_key, p.title, p.body,
                       p.difficulty, p.exam_weight, p.sort_no,
                       COALESCE(g.mastered, 0) AS mastered, g.note, g.updated_at
                FROM study_point p
                LEFT JOIN study_point_progress g ON g.point_id=p.id AND g.user_id=?
                WHERE p.course_code=?
                ORDER BY p.chapter_no, p.sort_no, p.id
                """, POINT_MAPPER, userId, code);

        Map<Integer, MutableChapter> grouping = new LinkedHashMap<>();
        for (PointView point : points) {
            grouping.computeIfAbsent(point.chapterNo(),
                            key -> new MutableChapter(point.chapterNo(), point.chapterTitle()))
                    .points.add(point);
        }
        List<ChapterView> chapters = new ArrayList<>();
        grouping.values().forEach(chapter ->
                chapters.add(new ChapterView(chapter.chapterNo, chapter.chapterTitle, chapter.points)));
        return new CourseDetailView(meta, chapters);
    }

    /** 勾选 / 取消某个知识点的掌握状态。 */
    public PointProgressView saveProgress(long userId, StudyController.ProgressInput input) {
        Long pointId = input.pointId();
        Boolean mastered = input.mastered();
        Integer exists = jdbc.queryForObject("SELECT COUNT(*) FROM study_point WHERE id=?", Integer.class, pointId);
        if (exists == null || exists == 0) {
            throw new BusinessException(404, "STUDY_POINT_NOT_FOUND: 知识点不存在: " + pointId);
        }
        String note = input.note() == null || input.note().isBlank() ? null : input.note().trim();
        Timestamp now = Timestamp.from(Instant.now());
        jdbc.update("""
                INSERT INTO study_point_progress(user_id, point_id, mastered, note, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE mastered=VALUES(mastered), note=VALUES(note), updated_at=VALUES(updated_at)
                """, userId, pointId, mastered ? 1 : 0, note, now);
        if (!mastered && note == null) {
            // 取消掌握且没有笔记时直接删行，进度表只保留"有意义的状态"。
            jdbc.update("DELETE FROM study_point_progress WHERE user_id=? AND point_id=? AND mastered=0 AND note IS NULL",
                    userId, pointId);
        }
        return progressOf(userId, pointId);
    }

    /** 清空某门课的个人进度。 */
    public ResetView reset(long userId, String code) {
        int deleted = jdbc.update("""
                DELETE FROM study_point_progress
                WHERE user_id=?
                  AND point_id IN (SELECT id FROM study_point WHERE course_code=?)
                """, userId, code);
        return new ResetView(code, deleted);
    }

    private PointProgressView progressOf(long userId, long pointId) {
        List<PointProgressView> rows = jdbc.query("""
                SELECT p.id, p.course_code, p.title, COALESCE(g.mastered, 0) AS mastered, g.note, g.updated_at
                FROM study_point p
                LEFT JOIN study_point_progress g ON g.point_id=p.id AND g.user_id=?
                WHERE p.id=?
                """, PROGRESS_MAPPER, userId, pointId);
        if (rows.isEmpty()) throw new BusinessException(404, "STUDY_POINT_NOT_FOUND: 知识点不存在: " + pointId);
        return rows.get(0);
    }

    private List<CourseSummaryView> courseRows(long userId) {
        return jdbc.query("""
                SELECT c.code, c.title, c.category, c.summary, c.source, c.icon, c.sort_no,
                       (SELECT COUNT(*) FROM study_point p WHERE p.course_code=c.code) AS point_count,
                       (SELECT COUNT(*) FROM study_point_progress g JOIN study_point p ON p.id=g.point_id
                         WHERE p.course_code=c.code AND g.user_id=? AND g.mastered=1) AS mastered_count
                FROM study_course c
                ORDER BY c.category, c.sort_no, c.code
                """, COURSE_MAPPER, userId);
    }

    /* ── 行模型与视图 ─────────────────────────────────────────────────── */

    private static final RowMapper<CourseSummaryView> COURSE_MAPPER = (rs, rowNum) ->
            new CourseSummaryView(rs.getString("code"), rs.getString("title"), rs.getString("category"),
                    rs.getString("summary"), rs.getString("source"), rs.getString("icon"),
                    rs.getInt("sort_no"), rs.getInt("point_count"), rs.getInt("mastered_count"));

    private static final RowMapper<PointView> POINT_MAPPER = (rs, rowNum) -> new PointView(
            rs.getLong("id"), rs.getInt("chapter_no"), rs.getString("chapter_title"),
            rs.getString("point_key"), rs.getString("title"), rs.getString("body"),
            rs.getString("difficulty"), rs.getInt("exam_weight"), rs.getInt("sort_no"),
            rs.getInt("mastered") != 0, rs.getString("note"), instant(rs, "updated_at"));

    private static final RowMapper<PointProgressView> PROGRESS_MAPPER = (rs, rowNum) -> new PointProgressView(
            rs.getLong("id"), rs.getString("course_code"), rs.getString("title"),
            rs.getInt("mastered") != 0, rs.getString("note"), instant(rs, "updated_at"));

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static final class MutableChapter {
        private final int chapterNo;
        private final String chapterTitle;
        private final List<PointView> points = new ArrayList<>();

        private MutableChapter(int chapterNo, String chapterTitle) {
            this.chapterNo = chapterNo;
            this.chapterTitle = chapterTitle;
        }
    }

    public record CourseSummaryView(String code, String title, String category, String summary,
                                    String source, String icon, int sortNo, int pointCount, int masteredCount) {}

    public record PointView(long id, int chapterNo, String chapterTitle, String pointKey, String title,
                            String body, String difficulty, int examWeight, int sortNo,
                            boolean mastered, String note, Instant updatedAt) {}

    public record ChapterView(int chapterNo, String chapterTitle, List<PointView> points) {
        public ChapterView {
            points = List.copyOf(points);
        }
    }

    public record CourseDetailView(CourseSummaryView course, List<ChapterView> chapters) {}

    public record PointProgressView(long pointId, String courseCode, String title, boolean mastered,
                                    String note, Instant updatedAt) {}

    public record ResetView(String courseCode, int cleared) {}

    public record OverviewView(double masteredPercent, int courseCount, int pointCount, int masteredCount,
                              Map<String, List<CourseSummaryView>> categories) {}
}
