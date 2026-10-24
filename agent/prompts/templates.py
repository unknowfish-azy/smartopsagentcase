def build_prompt(
    template: str,
    **kwargs,
) -> str:

    return template.format(**kwargs)