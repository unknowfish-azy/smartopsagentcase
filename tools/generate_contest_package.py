"""Generate truthful, dependency-free contest PDFs and submission metadata."""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

FONT = r"C:\Windows\Fonts\simhei.ttf"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = "SimHei"
plt.rcParams["axes.unicode_minus"] = False

DESKTOP = Path(r"C:\Users\33908\Desktop")
OUT = DESKTOP / "SmartOpsAgent_Phase7.4_参赛材料"

TITLE = "智维Agent可信运维实验平台"
INTRO = "面向智能运维的大模型实验基础设施，覆盖数据治理、来源追踪、人工审核、独立评测、Safety/Leakage门禁、Evaluator冻结和模型契约检查。项目坚持证据优先、审批控制、执行后验证和可复现审计；当前阶段不虚构训练结果，明确区分Synthetic Candidate、独立Golden与REAL模型，为后续RAG、Inspector、Verification消融及SFT建立可信基础。"

def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def pdf(path: Path, heading: str, sections: list[tuple[str, list[str]]]) -> None:
    with PdfPages(path) as book:
        pages = [(heading, ["SmartOpsAgent Phase 7.4", "本文件只呈现已执行、可追溯的真实状态。"])] + sections
        for title, body in pages:
            fig = plt.figure(figsize=(8.27, 11.69), facecolor="white")
            fig.text(0.08, 0.93, title, fontsize=20, fontweight="bold", color="#16324F")
            y = 0.875
            for line in body:
                wrapped = [line[i:i+42] for i in range(0, len(line), 42)] or [""]
                for part in wrapped:
                    fig.text(0.09, y, part, fontsize=12, color="#202124", va="top")
                    y -= 0.035
                y -= 0.012
            fig.text(0.08, 0.04, "SmartOpsAgent | Phase 7.4 | 真实状态优先", fontsize=9, color="#667085")
            book.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    return

    # Legacy dependency-free writer retained below for reference.
    lines = [heading, "SmartOpsAgent Phase 7.4", "", "This document reports only verified project facts."]
    for title, body in sections:
        lines += ["", title] + body
    lines = [line[:110] for line in lines]
    objects = []
    content = ["BT", "/F1 10 Tf", "50 790 Td"]
    for i, line in enumerate(lines):
        if i:
            content.append("0 -16 Td")
        content.append(f"({esc(line.encode('ascii','replace').decode('ascii'))}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("ascii")
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(out)); out += f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out); out += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets[1:])
    out += f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "参赛作品信息.txt").write_text(
        f"参赛作品名称：{TITLE}\n\n参赛作品简介：{INTRO}\n\n缴费状态：需参赛方完成缴费后提交。\n百度网盘链接：待参赛方上传材料后填写，当前未生成外部链接。\n", encoding="utf-8")
    pdf(OUT / "技术报告.pdf", "技术报告：智维Agent可信运维实验平台", [
        ("一、项目定位", ["面向智能运维的大模型实验基础设施，解决数据来源不可追踪、评测泄漏、模型能力冒充和实验不可复现等问题。", "本阶段禁止正式 SFT、DPO，不把 Dry Run 或 Mock 结果写成模型成果。"]),
        ("二、技术架构", ["数据层：Candidate、Approved、Train、Validation、Test、Golden、Regression 角色隔离。", "治理层：Provenance、Evidence Quality、L1-L10 Difficulty、Safety、Duplicate、Leakage、Group-aware Split。", "评测层：Ground Truth Freeze、Evaluator Contract、Model Contract、不可覆盖 Experiment Artifact。"]),
        ("三、真实执行结果", ["Candidate 40；治理校验 Valid 40、Invalid 0、Duplicate 0、Unsafe 0。", "Approved 0；Train/Validation/Test 为 0/0/0；Safety 与 Leakage 为 NOT_RUN。", "Independent Golden 为 NOT_READY；REAL Model 为 BLOCKED；GPU/CUDA 不可用；SFT 为 BLOCKED。"]),
        ("四、可信性设计", ["Synthetic Candidate 明确标记来源，候选通过校验不会自动批准。", "同源 Golden 被标记为 evaluation-only、NOT_INDEPENDENT，不进入训练。", "模型输出不能修改 Ground Truth；实验配置冻结并禁止写入 API Key、Token、Password 等敏感字段。"]),
        ("五、后续路线", ["先完成真实人工审核、独立 Golden、Safety/Leakage、Group-aware Split，再执行 B0 Rule/SOP、B1 Prompt、B2 Real Agent。", "只有前置 Gate 全部满足后，才允许进入 Phase 8 消融实验。"]),
    ])
    pdf(OUT / "演示汇报PPT.pdf", "项目汇报：智维Agent可信运维实验平台", [
        ("01 现实问题", ["运维 Agent 不能只回答问题，还必须理解环境、证据、风险、审批、执行和验证。", "普通模型 Demo 难以回答：数据从哪里来？结果能否复现？工具成功是否真的完成任务？"]),
        ("02 核心方案", ["建立从 Dataset Governance 到 Evaluator Freeze、Model Contract 和 Baseline 的完整实验链路。", "Evidence First、Read-only First、Version Aware、Approval Required、Verification Required。"]),
        ("03 数据可信", ["40 条 Synthetic Candidate 完成 Provenance 与治理字段补齐。", "Approved 仍为 0，人工审核不会被自动化脚本绕过；同源 Golden 不作为独立 Benchmark。"]),
        ("04 门禁可信", ["Safety、Leakage、Split、Independent Golden、REAL Model 各自独立判定。", "前置条件不足时保持 NOT_RUN、NOT_READY 或 BLOCKED，不把未执行写成 0。"]),
        ("05 当前结果", ["治理验证：40 valid / 0 invalid / 0 duplicate / 0 unsafe。", "测试：Training 36 passed、Knowledge 13 passed、Inspector 20 passed。", "模型训练和性能提升尚未发生，因此不宣称提升率。"]),
        ("06 后续路线", ["Phase 8：RAG / Inspector / Verification Ablation。", "Phase 9：SFT；Phase 10：Preference Optimization；Phase 11：Final Evaluation。"]),
    ])
    pdf(OUT / "佐证材料.pdf", "佐证材料：SmartOpsAgent Phase 7.4", [
        ("一、测试佐证", ["python -m pytest tests/training -q：36 passed。", "python -m pytest tests/knowledge -q：13 passed。", "python -m pytest tests/inspector -q：20 passed。"]),
        ("二、数据佐证", ["Candidate 数量 40，source_type 为 SYNTHETIC。", "治理校验 40 valid、0 invalid、0 duplicate、0 unsafe。", "Approved=0；没有自动审批或伪造人工审核。"]),
        ("三、实验边界佐证", ["Safety=NOT_RUN、Leakage=NOT_RUN、Independent Golden=NOT_READY。", "REAL Model=BLOCKED；Prompt Baseline、Real Baseline、Ablation 均为 NOT_RUN。", "SFT=BLOCKED，符合本阶段禁止正式训练的约束。"]),
        ("四、可复现材料", ["reports/phase-7.4/before/ 保存修改前快照。", "reports/phase-7.4/ 保存 dataset-quality、baseline-preflight、phase status、comparison 等报告。", "migrate_candidate_governance.py 支持 --check 只读审计；Experiment Artifact 禁止敏感字段且不覆盖既有配置。"]),
    ])
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slides = [
        ("智维Agent可信运维实验平台", "让运维智能体的每一次判断，都有证据、有边界、可复现", ["Phase 7.4 参赛汇报", "数据治理 + 安全门禁 + 可复现实验"]),
        ("为什么需要可信的运维智能体？", "传统 Demo 能回答，不能证明“答对且可执行”。", ["证据不足时容易臆测", "工具成功不等于任务成功", "高风险操作需要审批与验证", "实验结果需要可追踪、可复现"]),
        ("我们的方案：一条可审计实验链", "从 Candidate 到 Baseline，每一步都有明确角色和 Gate。", ["Dataset Role / Provenance", "Safety / Leakage / Group-aware Split", "Ground Truth / Evaluator Freeze", "Model Contract / Immutable Artifact"]),
        ("数据可信：不把校验通过当成批准", "40 条 Synthetic Candidate 已完成治理字段补齐。", ["Valid 40 | Invalid 0 | Duplicate 0 | Unsafe 0", "Approved 0：必须真实人工审核", "同源 Golden 标记为 NOT_INDEPENDENT", "L1-L10 难度与 Evidence Quality 可追踪"]),
        ("门禁可信：未运行就保持未运行", "项目不会为了好看把 NOT_RUN 改成 0 或 PASS。", ["Safety = NOT_RUN", "Leakage = NOT_RUN", "Independent Golden = NOT_READY", "REAL Model = BLOCKED", "SFT = BLOCKED"]),
        ("已验证的工程能力", "先证明基础设施可信，再谈模型提升。", ["Training Tests 36 passed", "Knowledge Tests 13 passed", "Inspector Tests 20 passed", "只读迁移审计 --check", "Artifact 禁止 Secret 且不可原地覆盖"]),
        ("创新与落地价值", "把“模型能力”拆成可检查、可追责的工程契约。", ["Evidence First：证据质量进入数据契约", "Risk Controlled：审批与高风险动作绑定", "Verification Required：识别 False Success", "Replayable：每次实验固定版本与哈希"]),
        ("路线图与诚实边界", "当前成果是可信实验基础设施，不是虚构的训练指标。", ["下一步：人工审核、Independent Golden、Safety/Leakage、Split", "随后：B0 Rule/SOP → B1 Prompt → B2 Real Agent", "Phase 8 Ablation → Phase 9 SFT → Phase 10 Preference", "当前没有模型提升率可宣称"]),
    ]
    for idx, (title, subtitle, bullets) in enumerate(slides):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        bg = slide.background.fill; bg.solid(); bg.fore_color.rgb = RGBColor(247, 250, 252)
        box = slide.shapes.add_textbox(Inches(0.75), Inches(0.65), Inches(11.9), Inches(0.7))
        tf = box.text_frame; p = tf.paragraphs[0]; p.text = title; p.font.size = Pt(28); p.font.bold = True; p.font.color.rgb = RGBColor(22, 50, 79)
        sub = slide.shapes.add_textbox(Inches(0.78), Inches(1.48), Inches(11.7), Inches(0.55))
        sp = sub.text_frame.paragraphs[0]; sp.text = subtitle; sp.font.size = Pt(17); sp.font.color.rgb = RGBColor(71, 85, 105)
        body = slide.shapes.add_textbox(Inches(1.0), Inches(2.35), Inches(11.0), Inches(3.9))
        bt = body.text_frame; bt.clear()
        for j, bullet in enumerate(bullets):
            p = bt.paragraphs[0] if j == 0 else bt.add_paragraph(); p.text = "• " + bullet; p.font.size = Pt(21); p.font.color.rgb = RGBColor(31, 41, 55); p.space_after = Pt(14)
        foot = slide.shapes.add_textbox(Inches(0.78), Inches(7.05), Inches(11.7), Inches(0.25))
        fp = foot.text_frame.paragraphs[0]; fp.text = f"SmartOpsAgent | Phase 7.4 | {idx+1}/{len(slides)}"; fp.font.size = Pt(9); fp.font.color.rgb = RGBColor(100, 116, 139)
    prs.save(OUT / "演示汇报PPT.pptx")
    (OUT / "百度网盘链接说明.txt").write_text("作品材料文件夹百度网盘链接：待参赛方完成上传后填写。\n当前目录包含除视频外的生成材料。\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "title": TITLE, "intro_length": len(INTRO)}, ensure_ascii=False))

if __name__ == "__main__": main()
