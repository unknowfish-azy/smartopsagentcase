from scripts.build_sft_dataset import (
    DIALOG_SAMPLES,
    _normalize,
    build_answer,
    build_dialog_samples,
    build_samples,
    clean_title,
    is_eligible,
    load_empty_evidence_text,
    load_golden_questions,
    load_runtime_prompts,
    render_user_message,
)


def test_prompt_template_is_extracted_from_runtime_source():
    system_prompt, template = load_runtime_prompts()

    assert "你是智维Agent的AI运维助手" in system_prompt
    assert "{context}" in template and "{safe_message}" in template
    assert "知识库证据：" in template and "<user_input>" in template

    user = render_user_message(
        template,
        "nginx 502 怎么排查？",
        "[证据 1]\n来源：reference/a.md\n版本：reference\n内容：upstream 不可达",
    )
    # 与 ChatService._build_prompt 一致：开头即固定要求段，用户问题被结构化包裹。
    assert user.startswith("\n请回答下面的用户问题。")
    assert "<user_input>\nnginx 502 怎么排查？\n</user_input>" in user


def test_samples_are_chatml_and_never_reuse_golden_questions():
    system_prompt, template = load_runtime_prompts()
    golden = load_golden_questions()

    samples, _ = build_samples(
        questions_per_section=1,
        max_per_doc=1,
        system_prompt=system_prompt,
        user_template=template,
        golden_questions=golden,
    )

    assert samples, "语料应能产出样本"
    for sample in samples:
        assert [item["role"] for item in sample["messages"]] == [
            "system",
            "user",
            "assistant",
        ]
        assert sample["messages"][2]["content"].startswith("根据《")
        question = sample["messages"][1]["content"].split("<user_input>")[1]
        question = question.split("</user_input>")[0].strip()
        assert _normalize(question) not in golden


def test_clean_title_removes_nested_numbering():
    assert clean_title("5.3、Docker容器操作") == "Docker容器操作"


def test_pure_command_output_and_unsafe_sections_are_rejected():
    dump = "```bash\n" + "root@host:~# docker ps -a\n" * 40 + "```"
    assert is_eligible("查看构建历史", dump) is False

    unsafe = "先确认服务状态，然后执行以下命令清理目录：" + "说明文字" * 40 + "\n```\nrm -rf /\n```"
    assert is_eligible("清理磁盘空间", unsafe) is False


def test_answer_lead_matches_content_shape():
    steps = "1. 先看监听端口\n2. 再看 upstream\n"
    assert "操作步骤" in build_answer(steps * 20, "Nginx 排障")

    prose = "容器是镜像的运行实例，独立运行一组应用以及其运行环境。" * 10
    assert "说明如下" in build_answer(prose, "Docker 基础")


def test_dialog_samples_use_runtime_prompt_and_empty_evidence():
    system_prompt, template = load_runtime_prompts()
    empty_evidence = load_empty_evidence_text()
    samples, by_category = build_dialog_samples(
        system_prompt=system_prompt,
        user_template=template,
        empty_evidence=empty_evidence,
        repeat=1,
    )

    assert len(samples) == len(DIALOG_SAMPLES)
    assert sum(by_category.values()) == len(samples)
    # 日常交流 + 学习能力两类都必须有样本，否则本次扩数据的口子没落地。
    for required in ("greeting", "thanks", "capability", "clarify", "emotion",
                     "smalltalk", "unknown", "learn_ask", "learn_confirm",
                     "correct", "reflect", "refuse"):
        assert by_category.get(required), f"缺少 {required} 类样本"

    for sample in samples:
        assert [item["role"] for item in sample["messages"]] == ["system", "user", "assistant"]
        assert sample["messages"][0]["content"] == system_prompt
        user_text = sample["messages"][1]["content"]
        assert f"知识库证据：\n{empty_evidence}" in user_text
        assert sample["messages"][2]["content"].strip()


def test_dialog_samples_never_claim_actions_that_did_not_happen():
    forbidden = ("已重启", "已修复", "已经执行", "已执行", "已经帮你重启")
    for item in DIALOG_SAMPLES:
        for phrase in forbidden:
            assert phrase not in item["assistant"], f"{item['user']} 出现了未发生的事实陈述"


def test_dialog_repeat_oversamples():
    system_prompt, template = load_runtime_prompts()
    samples, _ = build_dialog_samples(
        system_prompt=system_prompt,
        user_template=template,
        empty_evidence=load_empty_evidence_text(),
        repeat=3,
    )
    assert len(samples) == len(DIALOG_SAMPLES) * 3
