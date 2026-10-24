package com.smartops.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 测试辅助：把服务端下发的 SVG 场景解析回"图形中心 + 颜色 + 字符"，并依据提示挑出目标坐标，
 * 用来模拟"看懂提示后点击"的作答。
 *
 * <p>解析规则来自 {@link LocalGraphicalVerificationProvider} 的渲染实现：circle 的 cx/cy 就是中心；
 * rect 的 x/y 是左上角；polygon 用顶点坐标的几何中心（重心），对菱形与三角形都成立。</p>
 *
 * <p>提示解析刻意不依赖中文措辞：单目标提示里带 {@code #rrggbb}，多目标提示是"按字符"或"按颜色"，
 * 三种形态用结构与 ASCII 判别，避免测试对文案变化过度敏感。</p>
 */
public final class LocalScene {
    private static final Pattern CIRCLE = Pattern.compile("<circle cx=\"(\\d+)\" cy=\"(\\d+)\" r=\"\\d+\" fill=\"(#[0-9a-f]{6})\"");
    private static final Pattern RECT = Pattern.compile("<rect x=\"(-?\\d+)\" y=\"(-?\\d+)\" width=\"\\d+\" height=\"\\d+\" rx=\"\\d+\" fill=\"(#[0-9a-f]{6})\"");
    private static final Pattern POLYGON = Pattern.compile("<polygon points=\"((-?\\d+),(-?\\d+) [^\"]*)\" fill=\"(#[0-9a-f]{6})\"");
    private static final Pattern LABEL = Pattern.compile("dominant-baseline=\"central\">(\\w)</text>");
    private static final Pattern PROMPT_COLOR = Pattern.compile("(#[0-9a-f]{6})");
    private static final Pattern COORDINATE = Pattern.compile("(-?\\d+),(-?\\d+)");
    /** 提示里的颜色词与渲染用的十六进制色值一一对应；只用于"按颜色点选"的提示。 */
    private static final String[][] COLOR_NAMES = {
            { "红色", "#e2453c" }, { "蓝色", "#2f6fe0" }, { "绿色", "#2f9e5f" },
            { "橙色", "#e88b1f" }, { "紫色", "#8b5cf6" }, { "青色", "#0ea5b7" } };

    private LocalScene() {}

    /** 解析出场景中的图形（顺序与服务端渲染顺序一致）。 */
    public static List<Shape> shapes(String svg) {
        List<Shape> shapes = new ArrayList<>();
        List<Integer> starts = new ArrayList<>();
        Matcher circles = CIRCLE.matcher(svg);
        while (circles.find()) {
            shapes.add(new Shape(Integer.parseInt(circles.group(1)), Integer.parseInt(circles.group(2)), circles.group(3), ""));
            starts.add(circles.start());
        }
        Matcher rects = RECT.matcher(svg);
        while (rects.find()) {
            shapes.add(new Shape(Integer.parseInt(rects.group(1)) + LocalGraphicalVerificationProvider.TARGET_RADIUS,
                    Integer.parseInt(rects.group(2)) + LocalGraphicalVerificationProvider.TARGET_RADIUS, rects.group(3), ""));
            starts.add(rects.start());
        }
        Matcher polygons = POLYGON.matcher(svg);
        while (polygons.find()) {
            // 用顶点坐标的几何中心（重心）作为中心：菱形与三角形都成立，不依赖顶点个数或属性顺序。
            List<int[]> vertices = new ArrayList<>();
            Matcher points = COORDINATE.matcher(polygons.group(1));
            while (points.find()) vertices.add(new int[] { Integer.parseInt(points.group(1)), Integer.parseInt(points.group(2)) });
            int centerX = (int) Math.round(vertices.stream().mapToInt(vertex -> vertex[0]).average().orElseThrow());
            int centerY = (int) Math.round(vertices.stream().mapToInt(vertex -> vertex[1]).average().orElseThrow());
            shapes.add(new Shape(centerX, centerY, polygons.group(4), ""));
            starts.add(polygons.start());
        }
        Matcher labels = LABEL.matcher(svg);
        List<String> letters = new ArrayList<>();
        while (labels.find()) letters.add(labels.group(1));
        if (letters.size() != shapes.size()) throw new IllegalStateException("shape and label count mismatch: " + letters.size() + " vs " + shapes.size());
        List<Integer> order = new ArrayList<>();
        for (int index = 0; index < starts.size(); index++) order.add(index);
        order.sort((left, right) -> Integer.compare(starts.get(left), starts.get(right)));
        List<Shape> sorted = new ArrayList<>();
        for (int index = 0; index < order.size(); index++) sorted.add(shapes.get(order.get(index)).withLetter(letters.get(index)));
        return sorted;
    }

    /**
     * 依据提示挑出应点击的坐标（顺序敏感）。
     *
     * <ul>
     *   <li>提示含 {@code #rrggbb}：按颜色+字符点选单个目标；</li>
     *   <li>提示含大写字母：按字符依次点选；</li>
     *   <li>其他：按颜色词依次点选。</li>
     * </ul>
     */
    public static List<int[]> solution(String prompt, List<Shape> shapes) {
        Matcher color = PROMPT_COLOR.matcher(prompt);
        List<int[]> clicks = new ArrayList<>();
        if (color.find()) {
            String expected = color.group(1).toLowerCase(Locale.ROOT);
            for (Shape shape : shapes) if (shape.color().equals(expected)) clicks.add(shape.click());
            return clicks;
        }
        // 多目标提示只有两种形态：按大写字符点选，或按颜色词点选。
        // 场景里每个字符都唯一，而中文提示文案（"请/依次/点击/图形"）不含任何 ASCII 大写字母，
        // 因此"该字符是否出现在提示里"就是判据，且按提示中的出现顺序取出即可保证顺序正确。
        for (int index = 0; index < prompt.length(); index++) {
            String token = String.valueOf(prompt.charAt(index));
            for (Shape shape : shapes) if (shape.letter().equals(token)) clicks.add(shape.click());
        }
        if (!clicks.isEmpty()) return clicks;
        // 按颜色词点选：顺序必须跟随提示里颜色词的出现次序。
        List<String[]> matched = new ArrayList<>();
        for (String[] entry : COLOR_NAMES) {
            int position = prompt.indexOf(entry[0]);
            if (position >= 0) matched.add(new String[] { Integer.toString(position), entry[1] });
        }
        matched.sort((left, right) -> Integer.compare(Integer.parseInt(left[0]), Integer.parseInt(right[0])));
        for (String[] entry : matched) {
            for (Shape shape : shapes) if (shape.color().equals(entry[1])) clicks.add(shape.click());
        }
        return clicks;
    }

    public record Shape(int x, int y, String color, String letter) {
        public int[] click() { return new int[] { x, y }; }
        Shape withLetter(String value) { return new Shape(x, y, color, value); }
    }
}
