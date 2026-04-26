"""
Один источник правды для локального прайса (XLS в ``normalized_offers``).

Файл ``zayavka77rybinsk.xls`` — это **выгрузка/заявка ТДМ** (колонки «Артикул», «Наименование», «Баз. цена», …),
а не каталог ИЭК. Имя источника в БД и дефолтный ``brand`` согласованы с этим.
"""

from __future__ import annotations

# Файл по умолчанию в корне репозитория (dev): положили рядом с compose — подхватится без .env.
ZAYAVKA_XLS_BASENAME = "zayavka77rybinsk.xls"

# Как строка появится в ``normalized_offers.source_name`` и в UI ``/sources``.
LOCAL_PRICE_SOURCE_NAME_DEFAULT = "ТДМ Рыбинск (заявка)"

# Если ``LOCAL_PRICE_DEFAULT_BRAND`` не задан и загружается zayavka — проставляем бренд для exact_vendor_brand и KPI.
LOCAL_PRICE_DEFAULT_BRAND_FOR_ZAYAVKA = "TDM"
