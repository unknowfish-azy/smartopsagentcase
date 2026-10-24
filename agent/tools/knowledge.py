class KnowledgeSearchTool:

    name = "knowledge.search"

    description = "从知识库检索相关运维知识"

    risk_level = "LOW"

    requires_approval = False

    def __init__(
        self,
        retriever=None,
    ):
        self.retriever = retriever

    def execute(
        self,
        query: str,
        top_k: int = 5,
    ):

        if self.retriever is None:
            return {
                "query": query,
                "results": [],
                "message": (
                    "Knowledge Retriever 尚未连接"
                ),
            }

        return self.retriever.search(
            query,
            top_k=top_k,
        )