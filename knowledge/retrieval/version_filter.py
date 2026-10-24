class VersionFilter:

    @staticmethod
    def filter(
        results,
        version: str | None,
    ):
        if not version or version == "latest":
            return results

        return [
            result
            for result in results
            if result.version == version
        ]