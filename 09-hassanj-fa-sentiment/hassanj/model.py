# -*- coding: utf-8 -*-
"""آموزش و ارزیابی مدل احساسات.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
روش ارزیابی — و صداقتی که در آن رعایت شده
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

دو عدد گزارش می‌شود، نه یکی:

**۱) آزمون درون‌توزیع** — همان تقسیم ۸۰/۲۰ روی دیتاست قالب‌محور. این عدد بالا
درمی‌آید و **گمراه‌کننده** است: واژه‌های آزمون تقریباً همان واژه‌های آموزش‌اند،
چون هر دو از یک مجموعهٔ حدوداً ۸۰ قطعه‌جمله ساخته شده‌اند. عدد این آزمون معیار
«کار می‌کند یا نه» است، نه معیار «دقت واقعی چند است».

**۲) آزمون بیرون‌از‌توزیع** — مجموعهٔ دست‌نویس ``stress.py`` که هیچ واژه‌اش در
آموزش نیست: جمله‌های کامل، نفی مرکب، استثنا، طنز. این عدد پایین‌تر است و
**همان چیزی است که باید به کاربر نشان داده شود**. تفاوت این دو عدد، دقیقاً
اندازهٔ فاصلهٔ دیتاست مصنوعی با زبان واقعی است.

اعتبارسنجی متقابل ۵ تایی هم روی کل داده اجرا می‌شود تا روشن شود نتیجه به یک
تقسیم خوش‌شانس وابسته نیست.
"""
from __future__ import annotations

import json
import os
import sys
import time

import joblib
import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, precision_recall_fscore_support)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from .config import (CV_FOLDS, LABELS, RANDOM_SEED, TEST_SIZE, metrics_path,
                     model_path)
from .dataset import get_dataset
from .normalize import tokenize
from .stress import STRESS


def make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(tokenizer=tokenize, token_pattern=None,
                           ngram_range=(1, 2), min_df=2, sublinear_tf=True)


def make_candidates() -> dict[str, object]:
    return {
        "MultinomialNB": MultinomialNB(alpha=0.3),
        "LinearSVM (calibrated)": CalibratedClassifierCV(
            LinearSVC(C=1.0, random_state=RANDOM_SEED), cv=3),
        "LogisticRegression": LogisticRegression(max_iter=1000, C=4.0,
                                                 random_state=RANDOM_SEED),
    }


def _evaluate(pipe, texts, labels) -> dict:
    """معیارهای یک مجموعه — با ماتریس درهم‌ریختگی برای دیدن جهت خطاها."""
    predicted = pipe.predict(list(texts))
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predicted, labels=list(LABELS), zero_division=0)
    return {
        "n": len(texts),
        "accuracy": round(float(accuracy_score(labels, predicted)), 4),
        "f1_macro": round(float(f1_score(labels, predicted, average="macro",
                                        zero_division=0)), 4),
        "per_class": {
            code: {"precision": round(float(precision[index]), 4),
                   "recall": round(float(recall[index]), 4),
                   "f1": round(float(f1[index]), 4)}
            for index, code in enumerate(LABELS)
        },
        "confusion": confusion_matrix(labels, predicted,
                                      labels=list(LABELS)).tolist(),
    }


def stress_samples() -> tuple[list[str], list[str]]:
    return [text for text, _ in STRESS], [label for _, label in STRESS]


def hard_cases() -> list[dict]:
    """نمونه‌های دشوار و آن‌چه مدل روی‌شان گفته — برای نمایش در صفحهٔ «مدل»."""
    return [{"text": text} for text in
            ("بد نبود، حتی می‌تونم بگم خوب هم بود", "خوب بود ولی گرون",
             "با اینکه ارسالش دو روز دیر شد ولی خودش اونقدر خوب بود که ناراحت نشدم",
             "کیفیت ساخت معمولیه، انتظار بیشتری داشتم ولی ناراضی هم نیستم",
             "سایز استانداردش برای من کمی بزرگ بود، ولی مشکلی نداشتم",
             "از نظر ظاهر هیچ فرقی با مدل قبلی نداره، باید ببینم کارایی‌اش چطوره")]


def train_all(df=None) -> dict:
    """آموزش سه نامزد، انتخاب بهترین با F1 آزمون، ذخیره و ثبت معیارها."""
    if df is None:
        df = get_dataset()
    X_train, X_test, y_train, y_test = train_test_split(
        df["text"], df["label"], test_size=TEST_SIZE,
        stratify=df["label"], random_state=RANDOM_SEED)

    X_stress, y_stress = stress_samples()

    results: dict[str, dict] = {}
    best_name, best_pipe, best_score = None, None, -1.0
    for name, classifier in make_candidates().items():
        pipe = Pipeline([("tfidf", make_vectorizer()), ("clf", classifier)])
        started = time.time()
        pipe.fit(X_train, y_train)
        fit_seconds = time.time() - started
        in_domain = _evaluate(pipe, X_test, y_test)
        results[name] = {
            "f1_macro": in_domain["f1_macro"],
            "accuracy": in_domain["accuracy"],
            "stress_f1_macro": _evaluate(pipe, X_stress, y_stress)["f1_macro"],
            "stress_accuracy": _evaluate(pipe, X_stress, y_stress)["accuracy"],
            "fit_seconds": round(fit_seconds, 2),
        }
        if in_domain["f1_macro"] > best_score:
            best_name, best_pipe, best_score = name, pipe, in_domain["f1_macro"]

    # اعتبارسنجی متقابل فقط برای برنده — برای صرفه‌جویی در زمان ساخت.
    cv_scores = cross_val_score(best_pipe, df["text"], df["label"],
                                cv=CV_FOLDS, scoring="f1_macro")

    #: فایل joblib نام کلاس‌های scikit-learn را در خودش دارد؛ پس نسخهٔ کتابخانه
    #: بخشی از قرارداد این فایل است. کنار خودِ مدل ذخیره می‌شود تا ناسازگاری
    #: *پیش از* تلاش برای بازکردن فایل تشخیص داده شود.
    joblib.dump({"pipeline": best_pipe, "sklearn_version": sklearn.__version__},
                model_path())

    in_domain = _evaluate(best_pipe, X_test, y_test)
    out_domain = _evaluate(best_pipe, X_stress, y_stress)

    metrics = {
        "best_model": best_name,
        "n_samples": len(df),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "labels": list(LABELS),
        "test_size": TEST_SIZE,
        "cv_folds": CV_FOLDS,
        "results": results,
        "in_domain": in_domain,
        "out_domain": out_domain,
        "cv": {"f1_macro_mean": round(float(cv_scores.mean()), 4),
               "f1_macro_std": round(float(cv_scores.std()), 4)},
        "classification_report": classification_report(
            y_test, best_pipe.predict(X_test), target_names=list(LABELS),
            zero_division=0),
        "vocabulary_size": int(len(best_pipe.named_steps["tfidf"]
                                   .get_feature_names_out())),
        "stress_n": len(X_stress),
        "trained_at": time.strftime("%Y-%m-%d %H:%M"),
        "data_note": "دیتاست سینتتیک و قالب‌محور است؛ هیچ کامنت واقعی کاربری در آن نیست "
                      "و این اعداد معیار کیفیت روی کامنت واقعی نیستند.",
    }
    with open(metrics_path(), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
    return metrics


def load_metrics() -> dict:
    if not os.path.exists(metrics_path()):
        train_all()
    with open(metrics_path(), encoding="utf-8") as handle:
        return json.load(handle)


def _discard_model(reason: str) -> None:
    """مدل بی‌استفاده دور ریخته می‌شود و دلیلش روی stderr ثبت می‌شود."""
    print(f"[hassanj] مدل ذخیره‌شده دور ریخته شد — {reason}", file=sys.stderr)
    try:
        os.remove(model_path())
    except OSError:
        pass


def load_model():
    """طبقه‌بند آموزش‌دیده؛ اگر نبود یا خوانده نشد، از نو آموزش می‌بیند.

    شرط «وجود فایل» کافی نیست. دو حالت واقعی که اینجا پوشش داده می‌شود:

    ۱) مدل با نسخهٔ دیگری از ``scikit-learn`` ذخیره شده باشد — ``joblib`` نام
       کلاس‌های کتابخانه را در فایل نگه می‌دارد و بین دو نسخه حتی کلاس‌های
       خصوصی عوض می‌شوند. بارگذاری با ``AttributeError`` می‌شکند و هر صفحهٔ
       تحلیل و مدل خطای ۵۰۰ می‌دهد.

    ۲) فایل ناقص یا خراب نوشته شده باشد.

    در هر دو حالت مدل ناسازگار کنار گذاشته و از نو ساخته می‌شود؛ یک بار
    آموزش چند ثانیه‌ای به‌مراتب بهتر از خرابیِ پایدار همهٔ صفحه‌های محصول است.
    """
    path = model_path()
    if os.path.exists(path):
        try:
            bundle = joblib.load(path)
        except Exception as error:          # noqa: BLE001 — هر شکستی خودترمیم است
            _discard_model(f"بارگذاری ناموفق ({type(error).__name__})")
        else:
            built_with = bundle.get("sklearn_version") if isinstance(bundle, dict) else None
            if built_with == sklearn.__version__:
                return bundle["pipeline"]
            _discard_model(
                f"نسخهٔ scikit-learn عوض شده: {built_with} → {sklearn.__version__}"
                if built_with else "نسخهٔ scikit-learn در فایل ثبت نشده")
    train_all()
    return joblib.load(model_path())["pipeline"]


# ------------------------------------------------------------------ استخراج لایه‌ها
def classifier_of(pipe):
    """طبقه‌بند واقعی — لایهٔ کالیبراسیون باز می‌شود.

    ترتیب مهم است: ``CalibratedClassifierCV`` خودش ``classes_`` دارد ولی ضریب
    تصمیم ندارد، پس اول باید باز شود. اگر با ``classes_`` شروع کنیم، پوشش
    کالیبراسیون دست‌نخورده می‌ماند و توضیح‌پذیری بی‌صدا از کار می‌افتد.
    """
    classifier = pipe.named_steps["clf"]
    calibrated = getattr(classifier, "calibrated_classifiers_", None)
    if calibrated:
        return getattr(calibrated[0], "estimator", classifier)
    return getattr(classifier, "estimator", classifier)


def classes_of(pipe) -> list[str]:
    classifier = pipe.named_steps["clf"]
    classes = getattr(classifier, "classes_", None)
    if classes is None:
        classes = getattr(classifier_of(pipe), "classes_", list(LABELS))
    return [str(code) for code in classes]


def decision_matrix(pipe) -> np.ndarray:
    """ضرایب تصمیم — سطر به‌ازای کلاس، ستون به‌ازای ویژگی.

    NB: ``feature_log_prob_`` · LR و SVM: ``coef_``. هر دو ماتریس «وزن هر
    ویژگی برای هر کلاس» هستند، پس یک مسیر مشترک برای توضیح و واژگان کافی است.
    """
    estimator = classifier_of(pipe)
    matrix = getattr(estimator, "coef_", None)
    if matrix is None:
        matrix = getattr(estimator, "feature_log_prob_", None)
    if matrix is None:
        raise AttributeError("این طبقه‌بند ضریب تصمیم ندارد")
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    return matrix


def predict_one(pipe, text: str) -> dict:
    """برچسب + احتمال هر کلاس — مرتّب از بیشترین."""
    probabilities = pipe.predict_proba([text])[0]
    classes = classes_of(pipe)
    pairs = sorted(zip(classes, probabilities), key=lambda pair: -pair[1])
    return {
        "label": pairs[0][0],
        "confidence": round(float(pairs[0][1]), 4),
        "proba": {code: round(float(value), 4) for code, value in pairs},
    }


def predict_many(pipe, texts: list[str]) -> list[dict]:
    """پیش‌بینی برای فهرستی از متن‌ها — یک فراخوانی مدل، نه N فراخوانی.

    تفاوتش با صدا زدن ``predict_one`` در یک حلقه فقط سرعت است، نه نتیجه.
    هر فراخوانی sklearn سرباری برای اعتبارسنجی و ساختن آرایه دارد؛ روی تحلیل
    گروهی چند صد ردیفی، همین سربار از خود محاسبه بیشتر می‌شود.
    """
    if not texts:
        return []
    probabilities = pipe.predict_proba(list(texts))
    classes = classes_of(pipe)
    rows = []
    for row in probabilities:
        best = int(np.argmax(row))
        rows.append({
            "label": classes[best],
            "confidence": round(float(row[best]), 4),
            "proba": {code: round(float(value), 4)
                      for code, value in zip(classes, row)},
        })
    return rows


def top_terms(pipe, label: str, k: int = 10) -> list[tuple[str, float]]:
    """واژگان متمایزکنندهٔ یک کلاس — انحراف از میانگین سایر کلاس‌ها."""
    features = pipe.named_steps["tfidf"].get_feature_names_out()
    matrix = decision_matrix(pipe)
    classes = classes_of(pipe)
    index = classes.index(label)
    others = np.delete(matrix, index, axis=0).mean(axis=0)
    discriminative = matrix[index] - others
    order = discriminative.argsort()[-k:][::-1]
    return [(str(features[position]), float(discriminative[position]))
            for position in order]


def vocabulary(pipe) -> set[str]:
    """واژگان مدل — برای سنجش این‌که چند توکن متن شناخته‌شده است."""
    return set(pipe.named_steps["tfidf"].get_feature_names_out())
