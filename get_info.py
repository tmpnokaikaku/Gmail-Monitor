import re

def extract_manaba(body_text):
    fields = {}

    # 掲示された内容
    match_notice = re.search(r'に、\[(.+?)\]が.+?されました', body_text)
    if match_notice:
        fields['掲示内容'] = match_notice.group(1)

    # コース名
    match_course = re.search(r'\[コース名\]\s*:\s*(.+)', body_text)
    if match_course:
        fields['コース名'] = match_course.group(1)

    # 課題名
    match_task = re.search(r'\[課題名\]\s*:\s*(.+)', body_text)
    if match_task:
        fields['課題名'] = match_task.group(1)

    # タイトル
    match_title = re.search(r'\[タイトル\]\s*:\s*(.+)', body_text)
    if match_title:
        fields['タイトル'] = match_title.group(1)

    # 作成者
    match_author = re.search(r'\[作成者\]\s*:\s*(.+)', body_text)
    if match_author:
        fields['作成者'] = match_author.group(1)

    # 受付終了日時
    match_due = re.search(r'\[受付終了日時\]\s*:\s*(.+)', body_text)
    if match_due:
        fields['受付終了日時'] = match_due.group(1)

    # ログインURL
    match_url = re.search(r'PC\s*:\s*(https?://\S+)', body_text)
    if match_url:
        fields['URL'] = match_url.group(1)

    return fields


def extract_cels(body_text):
    fields = {}

    def extract_japanese(text):
        """スラッシュがあれば左側（日本語）、無ければそのまま"""
        return text.split('/')[0].strip()

    # ジャンル名称
    match_genre = re.search(r'ジャンル名称：(.+)', body_text)
    if match_genre:
        fields['ジャンル名称'] = extract_japanese(match_genre.group(1).strip())

    # 表題
    match_title = re.search(r'表題：(.+)', body_text)
    if match_title:
        fields['表題'] = extract_japanese(match_title.group(1).strip())

    # 内容（基本的に日本語のみだが念のため）
    match_content = re.search(r'内容：(.+?)(?:掲示者所属名称|URL|添付有無|詳細はCELS|$)', body_text, re.DOTALL)
    if match_content:
        fields['内容'] = extract_japanese(match_content.group(1).strip())

    # 掲示者所属名称
    match_affil = re.search(r'掲示者所属名称：(.+)', body_text)
    if match_affil:
        fields['掲示者所属名称'] = extract_japanese(match_affil.group(1).strip())

    # 掲示者
    match_author = re.search(r'掲示者：(.+)', body_text)
    if match_author:
        fields['掲示者'] = extract_japanese(match_author.group(1).strip())

    # URL
    match_url = re.search(r'(https?://[^\s]+)', body_text)
    if match_url:
        fields['URL'] = match_url.group(1)

    return fields
