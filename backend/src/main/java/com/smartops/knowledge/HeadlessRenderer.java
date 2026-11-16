package com.smartops.knowledge;

/**
 * 受控无头渲染器接口（T33b）。
 *
 * <p>实现必须是进程隔离的只读渲染：导航目标只允许是已经过 {@code OutboundUrlPolicy} 校验的 URL；
 * 只提取标题与正文文本；渲染不可用时如实返回不可用，绝不回退伪造静态正文。</p>
 */
public interface HeadlessRenderer {

    /** 渲染器是否可用（node + 渲染脚本就绪）。不可用时调用方返回 RENDERER_UNAVAILABLE。 */
    boolean isAvailable();

    /** 清理指定用户的隔离 profile（登录会话删除时调用；不支持则默认空实现）。 */
    default void wipeProfile(long userId) {}

    /**
     * 渲染页面并提取标题与正文文本。
     *
     * @param storageStateJson 登录接续的 storage state JSON（可空 = 匿名渲染）
     * @throws com.smartops.exception.BusinessException 渲染失败（RENDER_TIMEOUT/RENDER_FAILED/INVALID_URL）
     */
    RenderedPage render(String url, String storageStateJson);

    /**
     * 打开受控的有头浏览器窗口供用户显式登录（不代填凭据）。
     * 用户登录并在窗口内操作后关闭窗口；会话由实现写入隔离 profile，等 {@link #exportLoginState} 读取。
     *
     * @return 一次性句柄（仅用于前端提示，不含凭据）
     */
    String startLogin(long userId);

    /**
     * 读取用户完成登录后的 storage state JSON；用户未确认（窗口未关/未登录）返回 null。
     */
    String exportLoginState(long userId);

    /** 渲染结果（title/text 均按不可信资料处理，调用方再脱敏）。 */
    record RenderedPage(String title, String text) {}
}
