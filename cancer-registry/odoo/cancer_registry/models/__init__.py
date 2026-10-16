# -*- coding: utf-8 -*-
from . import cr_bridge          # يجب أن يُحمَّل أولاً — يضيف crcore إلى sys.path
from . import cancer_registry    # مُولَّد من crcore/dictionary.py
from . import refdata_models
from . import ui_ext             # مكتوب يدوياً: المعاينة والأزرار الذكية
