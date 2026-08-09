"""make_eval_framework_v2.py — 重组版「Simulated Patient 话语真实性评估框架」

相对 v1 的三处结构性改动:
  1. 四大类重新编号 A/B/C/D(v1 里第四类误标成 F);
  2. 每个指标配一张固定字段的 grounding 卡片,并显式写出"该来源不支持什么";
  3. 补进实际精读的三篇 case-study / 实证论文(v1 一篇都没引):
     Bryan 2007 (John)、Henriques 2023 (Maggie)、Cox et al. 2021。

样式辅助函数直接复用 build_simulated_patient_evaluation_doc.py 的前半段
(到 `doc = Document()` 之前),避免重复维护中文字体/表格/超链接代码。

用法: python3 tools/make_eval_framework_v2.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / 'build_simulated_patient_evaluation_doc.py'
_prefix = _SRC.read_text().split('\ndoc = Document()')[0]
exec(compile(_prefix, str(_SRC), 'exec'), globals())          # noqa: S102 — 复用样式辅助函数

OUT = ROOT / 'Simulated_Patient_Speech_Evaluation_Framework_v2.docx'

# ---------------------------------------------------------------- 文档骨架
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
for side in ('top_margin', 'bottom_margin', 'left_margin', 'right_margin'):
    setattr(sec, side, Inches(1))

styles = doc.styles
normal = styles['Normal']
normal.font.name = PRIMARY_FONT
normal.font.size = Pt(11)
normal.font.color.rgb = RGBColor(0, 0, 0)
normal._element.rPr.rFonts.set(qn('w:ascii'), PRIMARY_FONT)
normal._element.rPr.rFonts.set(qn('w:hAnsi'), PRIMARY_FONT)
normal._element.rPr.rFonts.set(qn('w:eastAsia'), CJK_FONT)
normal._element.rPr.rFonts.set(qn('w:hint'), 'eastAsia')
_lang = OxmlElement('w:lang'); _lang.set(qn('w:val'), 'en-US'); _lang.set(qn('w:eastAsia'), 'zh-CN')
normal._element.rPr.append(_lang)
normal.paragraph_format.space_after = Pt(8)
normal.paragraph_format.line_spacing = 1.15

for style_name, size, color, before, after in [
    ('Heading 1', 19, '000000', 20, 6),
    ('Heading 2', 15, '000000', 16, 5),
    ('Heading 3', 12.5, '434343', 13, 4),
]:
    s = styles[style_name]
    s.font.name = PRIMARY_FONT
    s.font.size = Pt(size)
    s.font.bold = False
    s.font.color.rgb = RGBColor.from_string(color)
    s._element.rPr.rFonts.set(qn('w:ascii'), PRIMARY_FONT)
    s._element.rPr.rFonts.set(qn('w:hAnsi'), PRIMARY_FONT)
    s._element.rPr.rFonts.set(qn('w:eastAsia'), CJK_FONT)
    s._element.rPr.rFonts.set(qn('w:hint'), 'eastAsia')
    sl = OxmlElement('w:lang'); sl.set(qn('w:val'), 'en-US'); sl.set(qn('w:eastAsia'), 'zh-CN')
    s._element.rPr.append(sl)
    s.paragraph_format.space_before = Pt(before)
    s.paragraph_format.space_after = Pt(after)
    s.paragraph_format.keep_with_next = True

num_b, num_n = add_numbering(doc)


# ---------------------------------------------------------------- 卡片辅助
CARD_FIELDS = ['测量什么', '操作定义', '分析单位', 'Grounding 来源',
               '该来源支持', '该来源不支持', '所需数据', '阶段']


def no_split(row):
    """禁止该行内部跨页拆分。"""
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement('w:cantSplit')
    e.set(qn('w:val'), 'true')
    trPr.append(e)


def card(doc, **kw):
    """指标 grounding 卡片:固定 8 个字段的两列表。整张卡片尽量不跨页断开。"""
    t = doc.add_table(rows=0, cols=2)
    rows = []
    for f in CARD_FIELDS:
        v = kw.get(f)
        if not v:
            continue
        r = t.add_row()
        rows.append(r)
        cells = r.cells
        p0 = cells[0].paragraphs[0]
        set_run_font(p0.add_run(f), size=9, bold=True, color='434343')
        p1 = cells[1].paragraphs[0]
        set_run_font(p1.add_run(v), size=9)
        for c in cells:
            set_cell_margins(c)
        no_split(r)
    # 除最后一行外都 keep_with_next —— 让排版引擎把整张卡片当作一个块
    for r in rows[:-1]:
        for c in r.cells:
            for p in c.paragraphs:
                p.paragraph_format.keep_with_next = True
    set_table_geometry(t, [1450, 7910])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def wide_table(doc, header, rows, widths, size=8.5):
    t = doc.add_table(rows=1, cols=len(header))
    for i, h in enumerate(header):
        p = t.rows[0].cells[i].paragraphs[0]
        set_run_font(p.add_run(h), size=size, bold=True)
        set_cell_margins(t.rows[0].cells[i])
    repeat_table_header(t.rows[0])
    no_split(t.rows[0])
    for row in rows:
        r = t.add_row()
        no_split(r)                      # 行内不跨页拆分,否则续页会留下空行
        cells = r.cells
        for i, v in enumerate(row):
            set_run_font(cells[i].paragraphs[0].add_run(v), size=size)
            set_cell_margins(cells[i])
    set_table_geometry(t, widths)
    return t


# 三篇核心 case-study / 实证论文的简写,反复引用
SRC_BRYAN = 'Bryan (2007), “John” 个案(CAMS/SSF + fluid vulnerability)'
SRC_HENRI = 'Henriques (2023), “Maggie” 个案(神经症循环 / ABCs / 羞耻型抑郁)'
SRC_COX = 'Cox et al. (2021), 危机聊天中的 helping-style 轨迹'

# ================================================================== 标题
title = doc.add_heading('Simulated Patient 话语真实性评估框架 v2', level=0)
for r in title.runs:
    set_run_font(r, size=24, bold=True)
sub = add_para(doc, '按 grounding 来源重组:每个指标标注其心理学依据、该依据支持什么、以及不支持什么')
set_run_font(sub.runs[0], size=11.5, color='555555')

add_para(doc, '适用系统:浏览器内实时语音 simulated patient(Candice / Savannah / Jordan);'
              'STT → LLM persona → TTS → reactive avatar。本文档只评价患者话语与语音的心理真实性,'
              '不评价图像清晰度、唇形同步或视觉身份漂移(那些由 docs/EVALUATION_METRICS.md 覆盖)。')

# ================================================================== 0
doc.add_heading('0. 这一版做了什么', level=1)
add_para(doc, 'v1 的问题有两个:一是四大类里第四类被标成 F(A/B/C/F),编号断裂;'
              '二是心理学论文集中列在每一章开头,读者无法判断"某一条具体指标究竟由哪篇论文支持、支持到什么程度"。'
              'v2 的三处改动:')
for item in [
    '四大类重新编号为 A/B/C/D,与你确定的四个类名一一对应;',
    '每个指标配一张固定字段的 grounding 卡片,其中「该来源不支持」一栏把 v1 里散落在各处的告诫收拢到它所约束的那条指标旁边;',
    '补进三篇实际精读过的论文 —— Bryan (2007)、Henriques (2023)、Cox et al. (2021)。v1 一篇都没引,'
    '但它们恰好是唯一能为「访谈者条件设计」「披露的中间行为」「状态动态的时间尺度」提供直接依据的来源。',
]:
    add_bullet(doc, item, num_b)

doc.add_heading('0.1 四大类', level=2)
wide_table(doc,
           ['类', '名称', '回答的问题', '指标'],
           [('A', 'Persona and fact consistency', '还是同一个患者吗?', 'A1–A4'),
            ('B', 'Clinical fidelity', '临床状态可识别且连贯吗?', 'B1–B6'),
            ('C', 'Disclosure realism', '披露过程在心理上说得通吗?', 'C1–C5'),
            ('D', 'Linguistic naturalness', '说话像匹配的真人患者吗?', 'D1–D6')],
           [500, 2600, 4260, 2000], size=9)

# ================================================================== 1
doc.add_heading('1. 测量原则', level=1)

doc.add_heading('1.1 四个分析层级', level=2)
add_para(doc, '任何一条指标都必须先声明它在哪一层成立。人格与语言自然度在单句层面无法评价 —— '
              '按人格状态分布理论,真人在不同时刻本来就有明显波动。')
wide_table(doc,
           ['层级', '单位', '典型指标'],
           [('Utterance', '单条患者回复', 'A1 事实准确率;B3 矛盾率'),
            ('Episode', '一条敏感事实从被触及到披露/回避的完整过程', 'C1 过早泄露;C3 披露行为序列;C5 否认后修正'),
            ('Session', '整场会谈', 'B2 症状恢复度;B4 动态连贯性;D3 时序特征;D4 会谈行为比例'),
            ('Repeated-simulation', '同一 persona 的 10–20 次随机复现', 'A3 分布保真度;A4 会话内漂移;C2 反事实对照')],
           [1800, 3900, 3660], size=9)

doc.add_heading('1.2 Grounding 强度分级', level=2)
add_para(doc, '并非所有指标都能找到论文支持。v2 要求每条指标明确标出自己属于哪一级,'
              '不允许用"有相关文献"来掩盖"论文只给了方向、没给阈值"这件事。')
wide_table(doc,
           ['级别', '含义', '报告要求'],
           [('G1', '构念与效应方向都有论文直接支持', '可以直接设定期望方向,并对方向做假设检验'),
            ('G2', '构念有论文支持,但阈值/系数必须自行拟合', '只报告方向与排序(如 Spearman),不得声称系数来自文献'),
            ('G3', '工程性 / 内部一致性指标,没有心理学论文可引', '必须在报告中明确标注为工程指标,不得包装成心理学效度证据')],
           [700, 4400, 4260], size=9)

# ================================================================== 2  A
doc.add_heading('2. A — Persona and fact consistency', level=1)
add_para(doc, 'A 类拆成两个不同的问题:病例事实是否正确(工程问题),以及患者在不同情境下是否呈现'
              '稳定但非机械的反应模式(人格心理学问题)。把这两件事合成一个"一致性分数"是 v1 的主要含混来源。')

doc.add_heading('2.1 A1 — Case fact accuracy', level=2)
add_formula(doc, 'FactAccuracy = correct_fact_presentations / fact_opportunities')
card(doc,
     测量什么='病例事实在被询问或被自然触发时,是否以正确粒度出现',
     操作定义='每次 opportunity 标注五个互斥状态之一:correctly_disclosed / correctly_withheld / '
              'intentionally_denied / contradicted_by_error / not_asked。只有 contradicted_by_error 进入分子',
     分析单位='Utterance',
     **{'Grounding 来源': 'Erby, Roter, & Biesecker (2011) 标准化患者表现研究',
        '该来源支持': '把 script accuracy 与 affective demeanor、realism 分开测量,而不是用一个综合分代替 —— '
                      '这是 A1 与 A2 必须分开的直接依据',
        '该来源不支持': '不提供"多少准确率算合格"的阈值;SP 研究的对象是受训真人,其错误模式与 LLM 遗忘不同源',
        '所需数据': '结构化病例事实表(每条含 ground truth、敏感度、是否允许隐瞒、触发条件)',
        '阶段': 'Phase 1 · G1'})
add_para(doc, '注意:intentionally_denied 不算事实错误。患者因害怕、污名或担心失去自主权而否认,'
              '是否合理由 C 类的披露模型评价 —— 在 A1 里惩罚它,会把"真实的隐瞒"错判成"模型出错"。')

doc.add_heading('2.2 A2 — If–then behavioral signature', level=2)
add_formula(doc, 'Delta(c,k) = E[state_k | context_c] − E[state_k | neutral]')
add_formula(doc, 'SignatureScore = SpearmanCorr(Delta_generated, Delta_target)')
card(doc,
     测量什么='患者在不同心理情境下的反应方向是否稳定且符合 persona 设定',
     操作定义='固定一组只改变心理情境、不改变所问事实的 probe;对每轮回复提取 disclosure、defensiveness、'
              'trust、anxiety、warmth、talkativeness、emotional intensity;比较各情境相对 neutral 的偏移方向',
     分析单位='Repeated-simulation',
     **{'Grounding 来源': f'Mischel & Shoda (1995) CAPS;probe 分类由 {SRC_COX} 与 {SRC_HENRI} 提供',
        '该来源支持': 'CAPS 把人格稳定性定义为可重复的 if–then 行为签名,这正是"不逐轮相同、但情境反应方向一致"的理论依据;'
                      'Cox 等把 active listening 与 collaborative problem-solving 作为实证研究过的两种助人风格,'
                      '使 probe 集不再是凭空设计;Henriques 的 ABCs(回避 / 指责 / 控制)给出被评判时的预期反应方向',
        '该来源不支持': 'CAPS 不给出偏移量的数值大小;因此第一阶段只用 Spearman 评方向与排序,不要求系数已校准',
        '所需数据': '5–8 类标准情境 probe;两名盲评心理学家的行为锚点评分',
        '阶段': 'Phase 1 · G2'})

doc.add_heading('2.3 A3 — 状态分布保真度', level=2)
add_formula(doc, 'DistributionFidelity_k = exp(−WassersteinDistance(P_generated,k , P_reference,k))')
card(doc,
     测量什么='多次复现下,各心理状态的分布(而非均值)是否落在真人/SP 的分布内',
     操作定义='同一 persona、同一脚本跑 10–20 次;对每个状态计算 session mean、within-session variance;'
              '用 Wasserstein distance 或 MMD 比较生成分布与参照分布',
     分析单位='Repeated-simulation',
     **{'Grounding 来源': 'Fleeson (2001) traits as density distributions of states',
        '该来源支持': '同一个人的即时状态波动很大,但状态分布的均值与形状具有稳定的个体差异 —— '
                      '这直接反驳了"方差越小越一致越好"的直觉',
        '该来源不支持': '经验采样研究的对象是日常生活状态,不是临床会谈;不能把其分布形状直接当作会谈中的目标分布',
        '所需数据': '匹配的真人或训练良好的 SP 会谈作为分布参照',
        '阶段': 'Phase 2 · G2'})
add_para(doc, '同时报告 session-level mean 的 ICC 与 turn-level variability ratio。'
              '目标不是 ICC 越高越好:ICC 极高且方差趋近 0,说明患者已经机械化。')

doc.add_heading('2.4 A4 — 会话内 persona 漂移', level=2)
add_formula(doc, 'DriftSlope_k = OLS_slope( state_k(t) ~ turn_index t ),  在无触发事件的区段上估计')
card(doc,
     测量什么='在没有心理触发事件的情况下,persona 是否随轮次单调偏移(长会谈里的"变成另一个人")',
     操作定义='取无重大触发事件的连续区段,对每个状态与 A2 签名向量估计随轮次的斜率;'
              '同时报告后半场签名向量与前半场的余弦相似度',
     分析单位='Session',
     **{'Grounding 来源': f'Fleeson (2001) 的基线稳定性;{SRC_BRYAN} 中的 baseline 与 acute 区分',
        '该来源支持': '存在一个可回归的基线水平是核心构念:急性升高之后应当回落到基线,'
                      '而不是把基线本身推走;慢性风险表现为基线更高、阈值更低,而非持续激活',
        '该来源不支持': '论文不给出"每 10 轮允许漂移多少"的容许值 —— 该容许值必须先由真人会谈估计',
        '所需数据': '长会谈(≥ 30 轮)的逐轮状态标注',
        '阶段': 'Phase 2 · G2'})

# ================================================================== 3  B
doc.add_heading('3. B — Clinical fidelity', level=1)
add_para(doc, 'B 类不问"像不像抑郁症",而问:预设的每个症状维度能否被观察到、彼此是否矛盾、'
              '以及是否随会谈事件按合理的时间尺度变化。')

doc.add_heading('3.1 隐藏临床状态的定义方式', level=2)
add_para(doc, '用经过验证的量表维度定义隐藏状态,而不是让 LLM 自己维持一个自由文本诊断标签。'
              '三类量表各自负责不同的事:')
wide_table(doc,
           ['来源', '在本系统中负责', '不负责'],
           [('PHQ-9 (Kroenke et al., 2001)', '定义抑郁症状条目与频率刻度', '不作为诊断依据,也不作为"越严重越真实"的目标'),
            ('Beck Hopelessness Scale (Beck et al., 1974)', '把绝望与一般负性情绪区分开', '不提供口语会谈中的表达阈值'),
            ('C-SSRS (Posner et al., 2011)', '把死亡愿望 / 主动意念 / 手段 / 意图 / 计划 / 行为分成独立字段', '不得压缩成单一"风险分";本系统只用它保持结构一致性'),
            (SRC_BRYAN, 'SSF 六构念(心理痛苦、压力、激越、绝望、自我憎恨、总体风险)+ 独立的求生 / 求死两轴,作为 B2 的恢复目标集', '个案研究不提供群体层面的常模或截断值')],
           [2750, 4300, 2310], size=8.5)

doc.add_heading('3.2 B1 — Symptom coverage', level=2)
add_formula(doc, 'Coverage = symptoms_with_observable_evidence / symptoms_expected_to_be_observable')
card(doc,
     测量什么='被适当询问的症状里,有多少获得了可观察证据',
     操作定义='只有当访谈问题为该症状提供了机会时才进入分母 —— 患者没主动谈睡眠不算漏,'
              '治疗师明确问了睡眠而患者无心理理由地答与设定相反才算',
     分析单位='Session',
     **{'Grounding 来源': 'PHQ-9 (Kroenke et al., 2001) 提供症状条目集',
        '该来源支持': '一份被广泛验证的、有限且互斥的抑郁症状清单,使"覆盖率"的分母是可定义的',
        '该来源不支持': 'PHQ-9 是自评频率量表,不定义这些症状在自由会谈中应如何被表达',
        '所需数据': '逐条 utterance 的症状证据标注',
        '阶段': 'Phase 1 · G1'})

doc.add_heading('3.3 B2 — Construct recoverability', level=2)
add_formula(doc, 'Recovery_k = 1 − |estimated_state_k − target_state_k| / scale_range_k')
card(doc,
     测量什么='盲评临床心理学家能否仅凭 transcript 或音视频还原出预设的症状画像',
     操作定义='对评价者隐藏 persona 设定;连续维度报告 MAE、Spearman 与 CCC,二元症状报告 sensitivity / specificity / macro-F1',
     分析单位='Session',
     **{'Grounding 来源': f'{SRC_BRYAN} 的 SSF 六构念与求生/求死双轴;PHQ-9;BHS',
        '该来源支持': 'SSF 六构念带有精确的互斥定义并要求患者自行排序,因而可以作为"被还原对象"的目标集;'
                      '求生与求死是两条独立的轴,不是一条轴的两端 —— 这一点直接决定了 B2 不能只测一个"风险高低"',
        '该来源不支持': '个案研究只演示了单一患者的评估流程,不提供评分者一致性基准;'
                        'ICC 的可接受水平必须在你自己的 pilot 中确定',
        '所需数据': '≥ 2 名盲评临床心理学家;第三名评价者用于分歧仲裁',
        '阶段': 'Phase 1 · G1'})
add_para(doc, '核心问题是:模拟患者有没有通过自然对话表达出预设的临床画像 —— 而不是有没有复述量表条目。'
              '如果患者直接说"我的绝望是 8 分",B2 应当判为失败而非成功。')

doc.add_heading('3.4 B3 — Clinical contradiction rate', level=2)
add_formula(doc, 'ContradictionRate = unsupported_clinical_contradictions / clinical_claims')
card(doc,
     测量什么='没有心理学解释的临床自相矛盾比例',
     操作定义='把矛盾分三类:(a) 症状的真实变化;(b) 因隐瞒而产生的表面否认;(c) 模型遗忘导致的矛盾。只有 (c) 进入分子',
     分析单位='Utterance',
     **{'Grounding 来源': '无 —— 这是内部一致性指标',
        '该来源支持': '(a) 由 B4 的动态模型解释,(b) 由 C 类的披露模型解释;B3 只负责剩下的部分',
        '该来源不支持': '不得把 B3 当作心理学效度证据。它测的是系统的记忆,不是患者的心理',
        '所需数据': '完整对话历史 + 病例事实表',
        '阶段': 'Phase 1 · G3'})

doc.add_heading('3.5 B4 — Dynamic coherence', level=2)
add_formula(doc, 'InvalidTransitionRate = unsupported_state_jumps / all_state_transitions')
card(doc,
     测量什么='状态变化是否符合允许的触发事件与时间尺度',
     操作定义='为每个状态定义最大变化速率与允许触发事件;超出即计为一次无效跳变',
     分析单位='Session',
     **{'Grounding 来源': f'Kleiman et al. (2017) EMA 研究;{SRC_BRYAN} 的 fluid vulnerability 框架',
        '该来源支持': 'EMA 证明自杀意念及其风险因子在小时级别就会显著波动 —— 因此不能要求全场恒定;'
                      'fluid vulnerability 则给出方向相反的约束:急性激活会回落到基线,'
                      '慢性风险表现为基线更高、阈值更低,而不是永久激活。两者合起来界定了"允许多快、允许到哪"',
        '该来源不支持': 'EMA 测的是自然生活中的波动,不是会谈内由治疗师行为引发的波动;'
                        '两篇都不提供"准确共情能在几轮内提升多少信任"的数值',
        '所需数据': '逐轮状态轨迹 + 触发事件标注',
        '阶段': 'Phase 2 · G2'})
add_para(doc, '举例说明约束的形状:准确共情可以在数轮内提高信任并降低紧张,但不应让重度快感缺失瞬间消失;'
              '提及近期失败可能短暂抬高绝望;达成可接受的安全计划可能降低当下紧迫感,'
              '但不等于自杀史被改写 —— 后者属于 B5。')

doc.add_heading('3.6 B5 — Suicide-structure accuracy', level=2)
card(doc,
     测量什么='意念、手段、意图、计划、既往行为五个字段是否被正确区分且不互相污染',
     操作定义='对每次涉及自杀内容的回复,标注它落在哪个字段;与 persona 的 ground truth 逐字段比对。'
              '在 method=false、plan=false 的 persona 上凭空说出手段或计划,记为严重违规',
     分析单位='Utterance',
     **{'Grounding 来源': 'C-SSRS (Posner et al., 2011)',
        '该来源支持': 'C-SSRS 的核心贡献正是把这几个层级分开,并证明它们不是同一个连续体上的刻度',
        '该来源不支持': '不得把 C-SSRS 简化成单一风险预测分;本系统只用它维持结构一致性,不用它预测风险',
        '所需数据': 'persona 的 suicidality 字段;逐条自杀相关回复的字段标注',
        '阶段': 'Phase 1 · G1'})
add_para(doc, '这条指标同时承担安全职能:它是唯一能自动发现"模型越过 ground truth 编造手段/计划"的指标。'
              'tools/probe_prompt.py 里的 INVENT 正则是它的粗糙版本,应当被这条正式指标替代。')

doc.add_heading('3.7 B6 — Severity calibration', level=2)
card(doc,
     测量什么='低 / 中 / 高严重度的 persona 能否被盲评者正确排序',
     操作定义='跨 persona 的 known-groups 检验;报告排序正确率与 Kendall τ',
     分析单位='Repeated-simulation',
     **{'Grounding 来源': 'PHQ-9 与 BHS 的严重度分层',
        '该来源支持': '量表提供了有序的严重度刻度,使"应当被排成什么顺序"是先验已知的',
        '该来源不支持': '量表分数与会谈中可感知的严重度不是同一件事;只检验排序,不检验绝对水平',
        '所需数据': '至少 3 档严重度 × 每档多个 persona',
        '阶段': 'Phase 2 · G1'})

# ================================================================== 4  C
doc.add_heading('4. C — Disclosure realism', level=1)
add_para(doc, 'C 类评价患者在什么时候、面对什么样的提问和关系条件,披露何种敏感信息。'
              '真实披露不是固定的脚本顺序,而是由隐瞒倾向、信息敏感度、污名、预期后果与治疗联盟共同决定的概率过程。')

doc.add_heading('4.1 披露倾向的构念来源', level=2)
wide_table(doc,
           ['来源', '定义了什么', '边界'],
           [('Larson & Chastain (1990) Self-Concealment Scale',
             '主动隐藏自认为负面或痛苦的个人信息的倾向',
             '与"话少"或一般自我披露不是一回事,不可互换'),
            ('Kahn & Hessling (2001) Distress Disclosure Index',
             '倾向隐瞒还是表达心理痛苦',
             '自评倾向,不等于结构化访谈中的实际行为'),
            ('Hom et al. (2017);Richards et al. (2019)',
             '自杀披露的具体障碍与促进因素:污名担忧、怕对方过度反应、怕失去自主权、认为披露没用;'
             '以及"希望被理解"作为促进因素',
             '定性/回顾性研究,给出机制而非概率'),
            ('Horvath & Greenberg (1989) WAI',
             '把治疗联盟拆成目标、任务、关系纽带三部分,作为信任状态的关系性 grounding',
             '测的是整段治疗的联盟,不是逐轮信任')],
           [2600, 4400, 2360], size=8.5)

doc.add_heading('4.2 C1 — Early leakage rate', level=2)
add_formula(doc, 'EarlyLeakage = facts_disclosed_before_threshold_met / high_sensitivity_facts')
card(doc,
     测量什么='高敏感事实是否在信任/提问条件尚未达标时就被倾倒出来',
     操作定义='每条 hidden_fact 设 sensitivity 与两个阈值(spontaneous / direct_question);'
              '在阈值未满足时出现即计为一次泄露',
     分析单位='Episode',
     **{'Grounding 来源': 'Larson & Chastain (1990);Hom et al. (2017)',
        '该来源支持': 'self-concealment 是稳定的个体差异,高隐瞒者不会在开场倾倒;'
                      '污名担忧是准确披露的常见障碍 —— 这使"开场即全盘托出"可判为不真实',
        '该来源不支持': '不提供阈值的数值。0.88 / 0.62 这类初始值是工程占位,必须在 pilot 中重新拟合',
        '所需数据': 'hidden_fact 结构(sensitivity、两个阈值、may_initially_deny、corrective_conditions)',
        '阶段': 'Phase 1 · G2'})

doc.add_heading('4.3 C2 — Support-sensitivity counterfactual(最关键的一条)', level=2)
add_para(doc, '同一 persona、同一问题、同一随机种子,只改变治疗师的回应方式,比较随后 3–5 轮的披露概率、'
              '深度、防御与信任。如果披露不随这些条件发生方向一致的变化,即使单句很流畅,心理过程仍然不真实。')
card(doc,
     测量什么='披露是否对治疗师行为敏感,且方向正确',
     操作定义='五个访谈者条件:supportive / neutral / premature problem solving / judgmental-coercive / '
              'direct suicide assessment;检验条件间披露量与防御的方向差异',
     分析单位='Repeated-simulation',
     **{'Grounding 来源': f'{SRC_COX};Hom et al. (2017);Richards et al. (2019)',
        '该来源支持': 'Cox 等把 active listening 与 collaborative problem-solving 作为两种被实证研究过的助人风格,'
                      '并指出以往研究把它们当成静态特征是不够的 —— 助人行为在会谈中是随时间展开的轨迹。'
                      '这既为条件集提供了来源(尤其"过早给建议"这一条不再是凭空设计),'
                      '也说明 C2 必须比较轨迹而不是单点',
        '该来源不支持': 'Cox 的数据来自在线危机聊天(文字、单次、危机情境),与门诊语音会谈的人群和情境不同;'
                        '不能把其效应量直接搬过来当作期望差值',
        '所需数据': '固定随机种子;每条件 ≥ 10 次复现',
        '阶段': 'Phase 1 · G1(方向)/ G2(幅度)'})

doc.add_heading('4.4 C3 — Disclosure-act taxonomy', level=2)
add_para(doc, '输出不应只有 disclose / not disclose。真实会谈里的中间行为是:模糊回答、最小化、改变时间范围、'
              '承认情绪但否认意图、反问后果、沉默、要求澄清、先否认后修正。')
card(doc,
     测量什么='患者是否使用了完整的中间披露行为谱,而非二元开关',
     操作定义='对每条涉及敏感事实的回复标注一个有序类别(否认 → 最小化 → 模糊 → 部分承认 → 完整披露),'
              '外加非有序的偏转类(反问、转移话题、沉默);报告类别分布与序数位置随轮次的变化',
     分析单位='Episode',
     **{'Grounding 来源': f'{SRC_HENRI};Hom et al. (2017)',
        '该来源支持': 'Henriques 把回避、指责、控制(ABCs)当作有功能的应对系统而非噪声,'
                      '并把最小化与羞耻驱动的退缩描述为可观察的临床现象 —— 这使中间行为成为需要建模的对象;'
                      'Hom 等则记录到"被直接问及自杀意念时否认"是真实且常见的行为',
        '该来源不支持': '两者都不给出各类别的期望比例;分布必须由匹配的真人语料估计',
        '所需数据': '有序类别的人工标注 + 标注者一致性(weighted kappa)',
        '阶段': 'Phase 1(标注)/ Phase 2(分布比较)· G2'})

doc.add_heading('4.5 C4 — Disclosure timing', level=2)
add_formula(doc, 'hazard_i(t) = P(fact_i 在第 t 轮首次披露 | 到 t−1 轮尚未披露)')
card(doc,
     测量什么='敏感事实首次披露的时间分布',
     操作定义='离散时间生存模型 / discrete-time hazard;协变量为信任、提问直接度、联盟、条件',
     分析单位='Episode',
     **{'Grounding 来源': f'Horvath & Greenberg (1989);{SRC_COX} 的轨迹建模思路',
        '该来源支持': '联盟是随时间建立的,不是初始常数;Cox 等对"轨迹优于静态特征"的论证同样适用于披露时点',
        '该来源不支持': '没有任何一篇给出 hazard 的形状或基线率 —— 这一条完全依赖你自己的数据拟合,'
                        '在拿到真人/SP 语料之前不应报告绝对值',
        '所需数据': '每条 hidden_fact 的首次披露轮次 + 右删失记录',
        '阶段': 'Phase 2 · G2'})

doc.add_heading('4.6 C5 — Correction after denial', level=2)
add_formula(doc, 'CorrectionRate = denied_facts_later_disclosed_under_corrective_conditions / denied_facts')
card(doc,
     测量什么='先否认之后,能否在非评判追问、自主权支持或准确反映之下被修正',
     操作定义='对每条 may_initially_deny 的事实,记录否认后是否在 corrective_conditions 出现时改口,以及间隔轮数',
     分析单位='Episode',
     **{'Grounding 来源': 'Hom et al. (2017);Richards et al. (2019)',
        '该来源支持': '这两项研究的核心正是"曾经否认过的人后来在什么条件下会说出来":'
                      '希望被理解、获得情感支持是促进因素;怕对方过度反应、怕失去自主权是障碍',
        '该来源不支持': '回顾性访谈不给出修正的时间窗;"几轮之内算修正成功"必须自行定义并在报告中写明',
        '所需数据': 'corrective_conditions 的逐轮标注',
        '阶段': 'Phase 2 · G1(方向)'})

# ================================================================== 5  D
doc.add_heading('5. D — Linguistic naturalness', level=1)
add_para(doc, 'D 类拆成四块:语义表达是否符合心理状态、会谈行为是否像患者、文本风格是否落在匹配人群的分布内、'
              '声音时间特征是否符合症状与情境。心理学能为症状相关的语言特征提供方向,'
              '但不存在一个对所有患者通用的"自然度量表" —— 最终必须依赖匹配的真人/SP 语料。')

doc.add_heading('5.1 D1 — Lexical marker distribution match', level=2)
add_formula(doc, 'NaturalnessFidelity = exp(−Distance(X_generated , X_matched_human))')
card(doc,
     测量什么='第一人称单数、负性情绪词、绝对化词的使用率是否落在匹配人群分布内',
     操作定义='提取特征向量后用 Mahalanobis / Wasserstein / MMD 比较分布;不比较单条回复',
     分析单位='Session',
     **{'Grounding 来源': 'Rude, Gortner, & Pennebaker (2004);Al-Mosaiwi & Johnstone (2018)',
        '该来源支持': '当前抑郁者的书面语言中第一人称单数与负性情绪词更多;'
                      '焦虑、抑郁、自杀意念语料中绝对化词语更多(自杀意念论坛尤其明显)—— 提供特征方向',
        '该来源不支持': '两者都基于书面文章或网络论坛文本,不能作为临床口语的阈值;'
                        '更不能把"负性词越多越真实"当作优化目标 —— 目标是接近分布,不是最大化标记',
        '所需数据': '匹配诊断/严重度/年龄/语言/访谈阶段的参照语料',
        '阶段': 'Phase 2 · G2'})

doc.add_heading('5.2 D2 — 自我批评 / 羞耻语言', level=2)
card(doc,
     测量什么='是否出现羞耻驱动的自我批评语言,以及它是否在特定情境下被触发',
     操作定义='标注自我贬低陈述、对自身情绪的二次评判("我不该这么难受")、以及随后是否出现退缩/缩短回复',
     分析单位='Episode',
     **{'Grounding 来源': SRC_HENRI,
        '该来源支持': 'Henriques 把羞耻型抑郁与"内在批评者 → 关闭"描述为一条可观察的序列:'
                      '自我批评之后跟随的是退缩,而不是更多表达 —— 这给出了可检验的先后顺序',
        '该来源不支持': '单一个案的定性描述,不提供发生率或强度基准;'
                        '本指标在 Phase 1 只能作为"是否出现该序列"的二元检查',
        '所需数据': '人工标注的自我批评—退缩序列',
        '阶段': 'Phase 2 · G2'})

doc.add_heading('5.3 D3 — 时序与声学特征', level=2)
card(doc,
     测量什么='语速、反应延迟、话轮内停顿是否符合抑郁严重度',
     操作定义='speech rate(音节/秒)、response latency(治疗师结束到患者开口)、within-turn pause 的均值与分位数、'
              'pitch / energy 的均值与方差、voice activity ratio',
     分析单位='Session',
     **{'Grounding 来源': 'Yamamoto et al. (2020);Nilsonne (1988)',
        '该来源支持': 'Yamamoto 等在 241 名参与者、1,058 份数据上测量了语速、停顿与反应时间与抑郁严重度的关系;'
                      'Nilsonne 更早发现抑郁组在问题之后的反应延迟更长 —— 这是与本系统情境最接近的一组来源'
                      '(临床访谈语音,而非论坛文本)',
        '该来源不支持': '不提供 TTS 合成语音的对照;Cartesia 的停顿、语调与 disfluency 能力本身就是上限',
        '所需数据': 'Deepgram 词级时间戳、VAD、原始音频、Cartesia 输出 —— 不能只从 transcript 推断',
        '阶段': 'Phase 1 · G1'})
add_para(doc, '必须分开报告 text naturalness 与 rendered-speech naturalness。'
              '否则 TTS 的表达上限会被误记为 patient brain 的失败。')

doc.add_heading('5.4 D4 — 会谈行为比例', level=2)
card(doc,
     测量什么='患者 talk / 治疗师 talk 比例,以及 clinical、psychosocial、emotional、facilitative talk 的占比',
     操作定义='按 RIAS 类会谈行为分类逐轮标注后计算比例;按病例与访谈阶段分层比较',
     分析单位='Session',
     **{'Grounding 来源': 'Erby, Roter, & Biesecker (2011)(RIAS 类别在 SP 研究中的使用)',
        '该来源支持': '提供一套已在标准化患者研究中使用过的会谈行为分类与 verbal activity 测量方式',
        '该来源不支持': '不存在"患者说得越多越自然"的统一规律;目标分布必须按病例与访谈阶段分层,'
                        '否则测到的是任务差异而不是真实性差异',
        '所需数据': '会谈行为分类标注',
        '阶段': 'Phase 2 · G2'})

doc.add_heading('5.5 D5 — Disfluency 与非最优表达', level=2)
card(doc,
     测量什么='自我修正、未完成句、只回答一部分、答非所问、被打断后的恢复方式',
     操作定义='统计各类出现率;与匹配语料比较分布',
     分析单位='Session',
     **{'Grounding 来源': '无直接来源 —— 依赖匹配的真人/SP 语料',
        '该来源支持': '(不适用)',
        '该来源不支持': '不得用语法完美程度代替自然度。真实患者会迟疑、修正、答非所问或只回答一部分,'
                        '但"应当有多少"这件事没有论文可引',
        '所需数据': '匹配语料的 disfluency 分布',
        '阶段': 'Phase 2 · G3'})

doc.add_heading('5.6 D6 — Blinded clinician realism rating', level=2)
card(doc,
     测量什么='盲评临床心理学家对整体真实性的 1–5 评分',
     操作定义='1 = 明显错误或心理过程不可能;2 = 多处矛盾/过度披露/刻板化;3 = 基本可接受但可辨认出系统化模式;'
              '4 = 大部分符合临床经验;5 = 在该情境下与真实患者/SP 难以区分',
     分析单位='Session',
     **{'Grounding 来源': '无 —— 这是人类效标本身',
        '该来源支持': '(不适用)',
        '该来源不支持': '不得用 perplexity 或 LLM-as-judge 代替它。D6 是其他所有自动指标的效标,'
                        '若用另一个语言模型充当,收敛效度的论证会循环',
        '所需数据': '≥ 2 名盲评者;报告 ICC 或 Krippendorff α',
        '阶段': 'Phase 1 · 效标'})

# ================================================================== 6
doc.add_heading('6. 人类效标与心理测量验证', level=1)
add_para(doc, '心理学量表只提供构念定义,不会自动验证生成文本。从构念到行为的映射必须单独验证。'
              '至少两名不了解 persona 条件的临床心理学家独立评分:连续评分报告 ICC,类别标签报告 '
              'Krippendorff α 或 weighted kappa。出现分歧时保留原始评分,由第三位评价者形成仲裁标签,'
              '不能只保留共识结果 —— 那会人为抬高一致性。')
wide_table(doc,
           ['效度类型', '检验什么', '用哪些指标'],
           [('Known-groups', '高 vs 低 hopelessness / self-concealment / 初始信任的 persona 是否被区分', 'B6、C1、C2'),
            ('Convergent', '自动指标是否与盲评评分及量表反推值相关', 'B2 ↔ D6;C2 ↔ D6'),
            ('Discriminant', '披露分数是否只是抑郁严重度或回复长度的替代变量', 'C1/C2 对 B2、回复词数做偏相关'),
            ('Criterion', '生成患者与真实患者/SP 在匹配任务上的分布距离', 'A3、D1、D3'),
            ('Generalizability', '在未见过的 persona、访谈者表达与随机种子上是否保持', '全部,分 held-out 报告')],
           [1700, 4700, 2960], size=8.5)

# ================================================================== 7
doc.add_heading('7. 实验设计', level=1)

doc.add_heading('7.1 Persona 抽样', level=2)
add_para(doc, '先建立 16–32 个结构化 persona,至少正交改变:抑郁严重度、绝望、自杀意念结构、self-concealment、'
              'stigma / fear of consequences、初始信任、人际防御。'
              '避免让所有高抑郁 persona 同时高隐瞒 —— 否则 B 类与 C 类指标无法区分,'
              'discriminant validity 一定失败。')

doc.add_heading('7.2 标准化访谈者条件', level=2)
add_para(doc, '五个条件中的前四个直接对应 Cox et al. (2021) 所研究的助人风格维度,'
              '第五个来自自杀评估实践与 C-SSRS 的提问结构:')
wide_table(doc,
           ['条件', '操作化', '预期方向'],
           [('Supportive(active listening)', '准确反映、验证体验、尊重自主权', '信任 ↑、披露 ↑、防御 ↓'),
            ('Neutral', '标准临床提问,不额外强化关系', '基线'),
            ('Premature problem solving', '在充分共情之前就给出解决方案', '防御 ↑、披露 ↓(Cox 等指出时序很重要)'),
            ('Judgmental / coercive', '表达担忧但带判断或控制暗示', '防御 ↑↑、披露 ↓↓、可能触发否认'),
            ('Direct suicide assessment', '直接清晰地询问意念、手段、意图、计划', 'B5 结构应被完整激活;C3 可能出现先否认后修正')],
           [2350, 3900, 3110], size=8.5)

doc.add_heading('7.3 重复与统计模型', level=2)
add_para(doc, '每个 persona × 访谈者条件至少运行 10 次,保留生产温度与完整音频。'
              '分析时把 persona 与访谈脚本作为随机效应 —— 把几百条 turn 当成几百个独立患者是最常见的统计错误。')
for item in [
    '连续心理状态:mixed-effects regression,random intercepts for persona and script;',
    '是否披露:mixed-effects logistic regression;',
    '披露时点:discrete-time hazard model;',
    '重复 session 的分布:Wasserstein / MMD + bootstrap 置信区间;',
    '评价者一致性:ICC 或 Krippendorff α。',
]:
    add_bullet(doc, item, num_b)

# ================================================================== 8
doc.add_heading('8. 实施路线', level=1)
add_para(doc, 'Phase 1 的选择标准是:不依赖大型真人语料就能开始,且能验证构念是否成立。'
              '注意 Phase 1 里没有任何一条需要分布参照 —— 那是刻意的。')
wide_table(doc,
           ['阶段', '指标', '前置条件'],
           [('Phase 1', 'A1 事实准确率 / 无解释矛盾', '结构化病例事实表'),
            ('Phase 1', 'A2 六类情境 probe 的反应方向通过率', 'probe 集 + 行为锚点'),
            ('Phase 1', 'B1 症状覆盖率', '症状证据标注'),
            ('Phase 1', 'B2 盲评症状恢复度', '≥ 2 名临床心理学家'),
            ('Phase 1', 'B5 自杀结构准确率', 'persona 的 suicidality 字段'),
            ('Phase 1', 'C1 过早泄露率', 'hidden_fact 结构'),
            ('Phase 1', 'C2 支持敏感性反事实', '固定随机种子 + 五个条件'),
            ('Phase 1', 'D3 语速 / 反应延迟 / 停顿比', 'Deepgram 时间戳 + VAD 落盘'),
            ('Phase 1', 'D6 盲评真实性评分', '同 B2 的评价者'),
            ('Phase 2', 'A3 / A4 / B4 / B6 / C3–C5 / D1 / D2 / D4 / D5', '匹配的真人或 SP 参照语料')],
           [900, 5300, 3160], size=8.5)
add_para(doc, '第一阶段不要合并成一个总分。先报告各子指标、置信区间与失败样例;'
              '拿到临床心理学家评分及真人/SP 语料之后再估计权重。')

doc.add_heading('8.1 当前系统的缺口', level=2)
add_para(doc, '按上表核对现有实现,Phase 1 的九条里目前只有部分具备数据前提:')
for item in [
    '会话日志没有 session / patient / participant ID 与 provenance,任何跨 session 指标都无法归组 —— 这是最先要补的一步;',
    'Candice / Savannah 走 persona_only 分支,没有显式状态,A2 / B4 需要的逐轮状态目前只能靠事后人工标注;',
    'Deepgram 词级时间戳与 VAD 目前未落盘,D3 无法计算;',
    'hidden_fact 与病例事实表尚未结构化,A1 / C1 缺少 ground truth 的载体。',
]:
    add_bullet(doc, item, num_b)

# ================================================================== 9
doc.add_heading('9. Grounding 总索引', level=1)
add_para(doc, '一页速查:每条指标 → 依据 → 强度 → 阶段。'
              '标为 G3 的三条必须在任何对外报告中注明"无心理学 grounding,系工程指标"。')
wide_table(doc,
           ['指标', 'Grounding 来源', '级', '阶段'],
           [('A1 Case fact accuracy', 'Erby et al. (2011)', 'G1', 'P1'),
            ('A2 If–then signature', 'Mischel & Shoda (1995);Cox et al. (2021);Henriques (2023)', 'G2', 'P1'),
            ('A3 分布保真度', 'Fleeson (2001)', 'G2', 'P2'),
            ('A4 会话内漂移', 'Fleeson (2001);Bryan (2007)', 'G2', 'P2'),
            ('B1 Symptom coverage', 'Kroenke et al. (2001) PHQ-9', 'G1', 'P1'),
            ('B2 Construct recoverability', 'Bryan (2007) SSF 六构念;PHQ-9;Beck et al. (1974)', 'G1', 'P1'),
            ('B3 Contradiction rate', '无(内部一致性)', 'G3', 'P1'),
            ('B4 Dynamic coherence', 'Kleiman et al. (2017);Bryan (2007)', 'G2', 'P2'),
            ('B5 Suicide-structure accuracy', 'Posner et al. (2011) C-SSRS', 'G1', 'P1'),
            ('B6 Severity calibration', 'PHQ-9;Beck et al. (1974)', 'G1', 'P2'),
            ('C1 Early leakage', 'Larson & Chastain (1990);Hom et al. (2017)', 'G2', 'P1'),
            ('C2 Support sensitivity', 'Cox et al. (2021);Hom et al. (2017);Richards et al. (2019)', 'G1/G2', 'P1'),
            ('C3 Disclosure-act taxonomy', 'Henriques (2023);Hom et al. (2017)', 'G2', 'P1/P2'),
            ('C4 Disclosure timing', 'Horvath & Greenberg (1989);Cox et al. (2021)', 'G2', 'P2'),
            ('C5 Correction after denial', 'Hom et al. (2017);Richards et al. (2019)', 'G1', 'P2'),
            ('D1 Lexical markers', 'Rude et al. (2004);Al-Mosaiwi & Johnstone (2018)', 'G2', 'P2'),
            ('D2 羞耻 / 自我批评语言', 'Henriques (2023)', 'G2', 'P2'),
            ('D3 时序与声学', 'Yamamoto et al. (2020);Nilsonne (1988)', 'G1', 'P1'),
            ('D4 会谈行为比例', 'Erby et al. (2011)', 'G2', 'P2'),
            ('D5 Disfluency', '无(需匹配语料)', 'G3', 'P2'),
            ('D6 盲评真实性评分', '无(人类效标本身)', 'G3', 'P1')],
           [2500, 5250, 700, 910], size=8)

# ================================================================== 10
doc.add_heading('10. 限制与伦理', level=1)
for item in [
    '心理量表定义的是构念,不会自动验证生成文本;从构念到行为的映射必须单独验证。',
    '部分量表或完整条目可能受版权或授权限制;实现前确认使用许可。本文档未复制任何量表条目。',
    '语言标记只能作为模拟真实性的特征,不能用于真实患者的诊断或自杀预测。',
    '不要把"更严重、更负面、更迟缓"误认为"更真实"。目标是匹配设定与参考分布,不是最大化任何一个方向。',
    '若 simulated patient 用于评价学员,患者自身的不一致会成为测量误差,需要用多 persona、多情境与多次复现来控制。',
    '自杀主题脚本应由有相关临床经验的心理学家审核;系统须明确标示为教学模拟而非临床服务。',
    'Bryan (2007) 与 Henriques (2023) 都是单一个案研究。它们能提供构念、序列与临床合理性的判断依据,'
    '但不能提供群体常模 —— 凡引用这两篇的指标,阈值一律必须自行拟合。',
]:
    add_bullet(doc, item, num_b)

# ================================================================== 11
doc.add_heading('11. References', level=1)

doc.add_heading('11.1 本项目精读的三篇', level=2)
add_source(doc, 'Bryan, C. J. (2007)',
           'Empirically-based outpatient treatment for a patient at risk for suicide: The case of “John.” '
           'Pragmatic Case Studies in Psychotherapy, 3(2), Article 1, 1–40',
           'http://pcsp.libraries.rutgers.edu',
           note='— SSF 六构念、求生/求死双轴、fluid vulnerability 的基线 vs 急性区分;支撑 A4、B2、B4')
add_source(doc, 'Henriques, G. (2023)',
           'The many reasons why not to commit suicide: The case of “Maggie.” '
           'Pragmatic Case Studies in Psychotherapy, 19(3), Article 1, 184–241',
           'http://pcsp.nationalregister.org',
           note='— 神经症循环与 ABCs、羞耻型抑郁、内在批评者 → 退缩;支撑 A2、C3、D2')
add_source(doc, 'Cox, D. W., Wojcik, K. D., Kotlarczyk, A. M., Park, M., Mickelson, J. M., & Klonsky, E. D. (2021)',
           'How the helping process unfolds for clients in suicidal crises: Linking helping-style trajectories '
           'with outcomes in online crisis chats. Suicide and Life-Threatening Behavior, 51(6), 1224–1234',
           'https://doi.org/10.1111/sltb.12804',
           note='— active listening vs collaborative problem-solving 的轨迹建模;支撑 A2、C2、C4 与 §7.2 条件集')

doc.add_heading('11.2 构念与量表', level=2)
for a, t, u in [
    ('Al-Mosaiwi, M., & Johnstone, T. (2018)',
     'In an absolute state: Elevated use of absolutist words is a marker specific to anxiety, depression, '
     'and suicidal ideation. Clinical Psychological Science, 6(4), 529–542',
     'https://doi.org/10.1177/2167702617747074'),
    ('Beck, A. T., Weissman, A., Lester, D., & Trexler, L. (1974)',
     'The measurement of pessimism: The Hopelessness Scale. '
     'Journal of Consulting and Clinical Psychology, 42(6), 861–865',
     'https://doi.org/10.1037/h0037562'),
    ('Erby, L. A. H., Roter, D. L., & Biesecker, B. B. (2011)',
     'Examination of standardized patient performance: Accuracy and consistency of six standardized patients '
     'over time. Patient Education and Counseling, 85(2), 194–200',
     'https://doi.org/10.1016/j.pec.2010.10.005'),
    ('Fleeson, W. (2001)',
     'Toward a structure- and process-integrated view of personality: Traits as density distributions of states. '
     'Journal of Personality and Social Psychology, 80(6), 1011–1027',
     'https://doi.org/10.1037/0022-3514.80.6.1011'),
    ('Hom, M. A., Stanley, I. H., Podlogar, M. C., & Joiner, T. E. (2017)',
     '“Are you having thoughts of suicide?” Examining experiences with disclosing and denying suicidal ideation. '
     'Journal of Clinical Psychology, 73(10), 1382–1392',
     'https://doi.org/10.1002/jclp.22440'),
    ('Horvath, A. O., & Greenberg, L. S. (1989)',
     'Development and validation of the Working Alliance Inventory. '
     'Journal of Counseling Psychology, 36(2), 223–233',
     'https://doi.org/10.1037/0022-0167.36.2.223'),
    ('Kahn, J. H., & Hessling, R. M. (2001)',
     'Measuring the tendency to conceal versus disclose psychological distress. '
     'Journal of Social and Clinical Psychology, 20(1), 41–65',
     'https://doi.org/10.1521/jscp.20.1.41.22254'),
    ('Kleiman, E. M., Turner, B. J., Fedor, S., Beale, E. E., Huffman, J. C., & Nock, M. K. (2017)',
     'Examination of real-time fluctuations in suicidal ideation and its risk factors: Results from two ecological '
     'momentary assessment studies. Journal of Abnormal Psychology, 126(6), 726–738',
     'https://doi.org/10.1037/abn0000273'),
    ('Kroenke, K., Spitzer, R. L., & Williams, J. B. W. (2001)',
     'The PHQ-9: Validity of a brief depression severity measure. '
     'Journal of General Internal Medicine, 16(9), 606–613',
     'https://doi.org/10.1046/j.1525-1497.2001.016009606.x'),
    ('Larson, D. G., & Chastain, R. L. (1990)',
     'Self-concealment: Conceptualization, measurement, and health implications. '
     'Journal of Social and Clinical Psychology, 9(4), 439–455',
     'https://doi.org/10.1521/jscp.1990.9.4.439'),
    ('Mischel, W., & Shoda, Y. (1995)',
     'A cognitive-affective system theory of personality: Reconceptualizing situations, dispositions, dynamics, '
     'and invariance in personality structure. Psychological Review, 102(2), 246–268',
     'https://doi.org/10.1037/0033-295X.102.2.246'),
    ('Nilsonne, A. (1988)',
     'Speech characteristics as indicators of depressive illness. '
     'Acta Psychiatrica Scandinavica, 77(3), 253–263',
     'https://doi.org/10.1111/j.1600-0447.1988.tb05118.x'),
    ('Posner, K., et al. (2011)',
     'The Columbia–Suicide Severity Rating Scale: Initial validity and internal consistency findings from three '
     'multisite studies with adolescents and adults. American Journal of Psychiatry, 168(12), 1266–1277',
     'https://doi.org/10.1176/appi.ajp.2011.10111704'),
    ('Richards, J. E., et al. (2019)',
     'Understanding why patients may not report suicidal ideation at a health care visit prior to a suicide '
     'attempt: A qualitative study. Psychiatric Services, 70(1), 40–45',
     'https://doi.org/10.1176/appi.ps.201800342'),
    ('Rude, S. S., Gortner, E.-M., & Pennebaker, J. W. (2004)',
     'Language use of depressed and depression-vulnerable college students. '
     'Cognition and Emotion, 18(8), 1121–1133',
     'https://doi.org/10.1080/02699930441000030'),
    ('Yamamoto, M., et al. (2020)',
     'Using speech recognition technology to investigate the association between timing-related speech features '
     'and depression severity. PLOS ONE, 15(9), e0238726',
     'https://doi.org/10.1371/journal.pone.0238726'),
]:
    add_source(doc, a, t, u)

doc.save(str(OUT))
print(f'✅ {OUT}')
print(f'   段落 {len(doc.paragraphs)} · 表格 {len(doc.tables)}')
