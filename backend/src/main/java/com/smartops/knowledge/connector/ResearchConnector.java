package com.smartops.knowledge.connector;

import com.smartops.exception.BusinessException;
import com.smartops.knowledge.WebResearchService;
import com.smartops.security.SessionUser;

import java.util.List;

/**
 * 联网研究连接器抽象（T34a）。
 *
 * <p>每个形态是一个独立连接器实例：独立 {@link #id()} 形态标识、独立开关、独立错误码、独立测试；
 * 禁止合并成 if-else 大类。共享的是底层安全出站链（KnowledgeCrawlService.fetch），
 * 不共享业务状态（开关/凭证/缓存）。结果 kind 必须填形态标识，前端原样展示来源形态。</p>
 */
public interface ResearchConnector {

    /** 形态标识，如 DDG / GITHUB / BAIDU_PUBLIC / ZHIHU_OFFICIAL。 */
    String id();

    /** 是否启用（配置驱动，默认全关；显式开启才生效）。 */
    boolean isEnabled();

    /**
     * 检索。失败抛异常，由聚合层记入 errors（{@code <id>:<errorCode>}），不中断其他形态。
     */
    List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit) throws Exception;

    /**
     * 读取指定 URL 正文（形态 C 使用）。默认不支持，抛 CONNECTOR_FETCH_UNSUPPORTED。
     */
    default WebResearchService.WebPage fetch(SessionUser actor, String url) {
        throw new BusinessException(400, "CONNECTOR_FETCH_UNSUPPORTED");
    }

    /** 是否参与检索聚合（形态 C 仅做指定 URL 读取，不参与检索）。 */
    default boolean supportsSearch() {
        return true;
    }
}
