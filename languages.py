"""Configured, ordered language editions; unsupported codes fail explicitly."""
LANGUAGES = {
    'zh-CN': '简体中文', 'zh-TW': '繁體中文', 'en': 'English', 'ja': '日本語',
    'ko': '한국어', 'fr': 'Français', 'de': 'Deutsch', 'es': 'Español',
    'ru': 'Русский', 'ar': 'العربية',
}
# Program-generated edition titles: the model never translates the title, so a
# title can neither be dropped nor turned into a bracket-only line.
TITLE_I18N = {
    'zh-CN': '每日简报', 'zh-TW': '每日簡報', 'en': 'Daily Digest', 'ja': 'デイリーダイジェスト',
    'ko': '데일리 다이제스트', 'fr': 'Synthèse quotidienne', 'de': 'Tägliche Übersicht',
    'es': 'Resumen diario', 'ru': 'Ежедневный дайджест', 'ar': 'الملخص اليومي',
}
ALIASES = {'zh':'zh-CN','zh-cn':'zh-CN','zh-hans':'zh-CN','中文':'zh-CN','简体中文':'zh-CN',
           'zh-tw':'zh-TW','zh-hant':'zh-TW','繁体中文':'zh-TW','繁體中文':'zh-TW',
           '英文':'en','英语':'en','日文':'ja','日语':'ja','韩文':'ko','韩语':'ko',
           '法语':'fr','德语':'de','西班牙语':'es','俄语':'ru','阿拉伯语':'ar'}


def language_list(config):
    if config.get('multilingual_enabled', True) is not True:
        return ['zh-CN']
    values = config.get('news_languages', ['zh-CN', 'en'])
    if isinstance(values, str):
        import re
        values = re.split(r'[,，、\s]+', values)
    if not isinstance(values, list) or not values:
        raise ValueError('news_languages 需要至少一种语言')
    result = []
    for value in values:
        key = str(value).strip().lower()
        code = ALIASES.get(key, key)
        if code not in LANGUAGES:
            raise ValueError('不支持的新闻语言：' + str(value) + '；可选：' + ', '.join(LANGUAGES))
        if code not in result:
            result.append(code)
    if len(result) > 5:
        raise ValueError('每次最多推送5种语言，请减少 news_languages')
    return result
