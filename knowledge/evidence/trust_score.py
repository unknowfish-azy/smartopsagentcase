class TrustScoreCalculator:

    def calculate(
        self,
        evidences,
        answer_supported: bool,
    ) -> float:

        if not evidences:
            return 0.0

        evidence_score = sum(
            evidence.score
            for evidence in evidences
        ) / len(evidences)

        support_score = (
            1.0
            if answer_supported
            else 0.0
        )

        coverage = min(
            len(evidences) / 3.0,
            1.0,
        )

        score = (
            0.5 * evidence_score
            + 0.3 * support_score
            + 0.2 * coverage
        )

        return round(
            max(0.0, min(score, 1.0)),
            4,
        )