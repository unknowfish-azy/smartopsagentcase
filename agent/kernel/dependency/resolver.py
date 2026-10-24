from dataclasses import dataclass, field


@dataclass
class DependencySpec:
    component_id: str
    depends_on: list[str] = field(default_factory=list)


class DependencyResolver:

    def resolve(
        self,
        components: list[DependencySpec],
    ) -> list[str]:
        graph = {
            item.component_id: set(item.depends_on)
            for item in components
        }

        result: list[str] = []

        while graph:
            ready = [
                name
                for name, dependencies in graph.items()
                if not dependencies
            ]

            if not ready:
                raise ValueError(
                    "Plugin dependency cycle detected"
                )

            for name in sorted(ready):
                result.append(name)
                del graph[name]

                for dependencies in graph.values():
                    dependencies.discard(name)

        return result