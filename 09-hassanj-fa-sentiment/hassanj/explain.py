# -*- coding: utf-8 -*-
"""توضیح‌پذیری — چرا مدل این برچسب را داد، و چقدر باید به آن اعتماد کرد.

دو چیز کاملاً جدا اینجا سنجیده و هر دو به کاربر نشان داده می‌شود:

**۱) سهم هر واژه.** بردار TF-IDF متن در ضرایب تصمیم مدل ضرب می‌شود. حاصل برای
هر واژه یک عدد است: مثبت یعنی آن واژه مدل را به سمت برچسب گزارش‌شده هل داده و
منفی یعنی در جهت مخالف. این عدد «احتمال» نیست و «سهم درصدی» هم نیست — یک
امتیاز نسبی است که فقط برای *مقایسهٔ واژه‌ها با هم* معنا دارد. برچسب‌گذاری آن
به‌عنوان درصد، دقیقاً همان ادعای بی‌پایه‌ای است که این پروژه از آن پرهیز می‌کند.

**۲) پوشش واژگان.** چند درصد از توکن‌های متن در واژگان مدل وجود دارد. این عدد
از احتمال مدل مهم‌تر است: اندازه‌گیری روی مجموعهٔ سنجش نشان داد دقت مدل وقتی
پوشش زیر ۵۰٪ است حدود ۰٫۵۶ و وقتی بالای ۸۰٪ است ۱٫۰۰ است. یعنی مدل خودش
می‌داند کجا از عمق واژگانش بیرون رفته — و همان را به کاربر می‌گوید.
"""
from __future__ import annotations

import numpy as np

from .labels import confidence_band, fa_percent, verdict_sentence
from .normalize import clean, tokenize
from .model import classes_of, decision_matrix, predict_one


def weight_rows(pipe) -> tuple[np.ndarray, list[str]]:
    """وزن هر کلاس نسبت به رقبایش — یک منبع حقیقت برای همهٔ توضیح‌ها.

    تحلیل تک‌متن و تحلیل گروهی باید *دقیقاً* یک فرمول داشته باشند. اگر هرکدام
    وزن خودش را بسازد، دو توضیح ناسازگار برای یک متن یکسان به کاربر نشان داده
    می‌شود. پس ماتریس وزن یک بار اینجا ساخته و هر دو مسیر از آن تغذیه می‌کنند.
    """
    matrix = decision_matrix(pipe)
    classes = classes_of(pipe)
    rows = []
    for index in range(matrix.shape[0]):
        others = np.delete(matrix, index, axis=0)
        baseline = others.mean(axis=0) if others.size else np.zeros(matrix.shape[1])
        rows.append(matrix[index] - baseline)
    return np.vstack(rows), classes


def top_signals_many(pipe, texts: list[str], winners: list[str],
                     limit: int = 3) -> list[list[str]]:
    """واژه‌های مؤثر برای هر ردیف — همان فرمول تحلیل تک‌متن، ولی دسته‌ای.

    روی هر ردیف فقط توکن‌های *حاضر در همان متن* ضرب می‌شوند، پس هزینه با شمار
    واژه‌های متن بالا می‌رود، نه با اندازهٔ واژگان.
    """
    if not texts:
        return []
    weights, classes = weight_rows(pipe)
    vectorizer = pipe.named_steps["tfidf"]
    matrix = vectorizer.transform(list(texts))
    names = vectorizer.get_feature_names_out()
    out: list[list[str]] = []
    for row_index in range(matrix.shape[0]):
        start, end = matrix.indptr[row_index], matrix.indptr[row_index + 1]
        indices = matrix.indices[start:end]
        values = matrix.data[start:end]
        if not len(indices):
            out.append([])
            continue
        winner = winners[row_index] if row_index < len(winners) else classes[0]
        weight = weights[classes.index(winner)] if winner in classes else weights[0]
        scores = values * weight[indices]
        order = np.argsort(-scores)[:max(0, limit)]
        out.append([str(names[indices[position]]) for position in order
                    if scores[position] > 0])
    return out


def _attributions(pipe, text: str, winner: int | None = None) -> dict[str, float]:
    """امتیاز هر ویژگی (واژه یا عبارت) در جهت برچسب برنده.

    فرمول: ``x_j × (W[برنده, j] − میانگین W[سایر کلاس‌ها, j])``

    یعنی وزن ویژگی در کلاس برنده، نسبت به رقبایش. جملهٔ دوم مهم است: واژه‌ای
    که در همهٔ کلاس‌ها وزن یکسان دارد، سهم صفر می‌گیرد — چون چیزی را جدا نمی‌کند.
    """
    vectorizer = pipe.named_steps["tfidf"]
    weights, classes = weight_rows(pipe)

    row = vectorizer.transform([text])
    if row.nnz == 0:
        return {}

    if winner is None:
        winner = int(np.argmax(pipe.predict_proba([text])[0]))
    winner = min(winner, weights.shape[0] - 1)
    weight = weights[winner]

    indices = row.indices
    values = row.data
    scores = values * weight[indices]
    names = vectorizer.get_feature_names_out()
    return {str(names[index]): float(score)
            for index, score in zip(indices, scores)}


def _signals(attributions: dict[str, float], toward: bool, limit: int) -> list[dict]:
    """واژه‌های مؤثر — ``toward`` یعنی در جهت برچسب یا در جهت مخالف آن."""
    if not attributions:
        return []
    items = [(name, score) for name, score in attributions.items()
             if (score > 0) == toward and abs(score) > 1e-9]
    items.sort(key=lambda pair: -abs(pair[1]))
    top = items[:limit]
    strongest = max((abs(score) for _, score in top), default=1.0) or 1.0
    return [{
        "term": name,
        "score": round(score, 4),
        #: پهنا برای نوار رابط — نسبی به قوی‌ترین واژه، نه درصد احتمال.
        "share": round(abs(score) / strongest, 3),
        "is_phrase": " " in name,
    } for name, score in top]


def analyse(pipe, text: str, *, limit: int = 6) -> dict:
    """تحلیل کامل یک متن — همان چیزی که صفحهٔ «تحلیل متن» نشان می‌دهد."""
    raw = "" if text is None else str(text)
    cleaned = clean(raw)
    tokens = tokenize(raw)
    vocabulary = set(pipe.named_steps["tfidf"].get_feature_names_out())
    known = [token for token in tokens if token in vocabulary]
    coverage = (len(known) / len(tokens)) if tokens else 0.0

    result = predict_one(pipe, raw)
    band = confidence_band(result["confidence"])
    # ترتیب احتمال‌ها نزولی است، پس برنده همان کلاس اول است — همان که در
    # توضیح هم باید مرجع باشد. دوباره محاسبه نمی‌شود.
    classes = classes_of(pipe)
    attributions = _attributions(pipe, raw, winner=classes.index(result["label"]))

    #: وضعیت ورودی. این‌ها پیش از هر عددی به کاربر گفته می‌شود، چون تعیین
    #: می‌کنند آن عدد اصلاً ارزش خواندن دارد یا نه.
    if not raw.strip():
        state = "empty"
    elif not tokens:
        state = "no_signal"
    elif not known:
        state = "out_of_domain"
    elif coverage < 0.5:
        state = "thin_coverage"
    else:
        state = "ok"

    return {
        "text": raw,
        "cleaned": cleaned,
        "tokens": tokens,
        "known_tokens": known,
        "unknown_tokens": [token for token in tokens if token not in vocabulary],
        "coverage": round(coverage, 4),
        "coverage_text": fa_percent(coverage, decimals=0),
        "token_count": len(tokens),
        "known_count": len(known),
        "state": state,
        "label": result["label"],
        "confidence": result["confidence"],
        "proba": result["proba"],
        "band": band,
        "verdict": verdict_sentence(result["label"], result["confidence"], band),
        "toward": _signals(attributions, True, limit),
        "against": _signals(attributions, False, limit),
        "has_signals": bool(attributions),
        "truncated": False,
    }


def coverage_buckets(pipe, samples: list[tuple[str, str]]) -> list[dict]:
    """دقت مدل به تفکیک پوشش واژگان — روی یک مجموعهٔ سنجش.

    این تابع همان چیزی را می‌سازد که در صفحهٔ «مدل» به‌شکل نمودار می‌آید: نشان
    می‌دهد دقت مدل به *عمق واژگان* گره خورده است، نه فقط به خودِ متن.
    """
    vocabulary = set(pipe.named_steps["tfidf"].get_feature_names_out())
    edges = ((0.0, 0.5, "زیر ۵۰٪"), (0.5, 0.8, "۵۰ تا ۸۰٪"), (0.8, 1.01, "بالای ۸۰٪"))
    buckets = []
    for low, high, title in edges:
        hits, total = 0, 0
        for text, gold in samples:
            tokens = tokenize(text)
            if not tokens:
                continue
            coverage = len([t for t in tokens if t in vocabulary]) / len(tokens)
            if low <= coverage < high:
                total += 1
                if predict_one(pipe, text)["label"] == gold:
                    hits += 1
        buckets.append({"title": title, "n": total,
                        "accuracy": round(hits / total, 4) if total else None})
    return buckets


def misclassified(pipe, samples: list[tuple[str, str]], limit: int = 8) -> list[dict]:
    """خطاهای مدل روی مجموعهٔ سنجش — با پوشش واژگان هر خطا.

    عمداً نمایش داده می‌شود. مدلی که فقط موفقیت‌هایش را نشان می‌دهد، ابزار
    تصمیم‌گیری نیست؛ تبلیغ است.
    """
    from .labels import sentiment_label

    vocabulary = set(pipe.named_steps["tfidf"].get_feature_names_out())
    out = []
    for text, gold in samples:
        result = predict_one(pipe, text)
        if result["label"] == gold:
            continue
        tokens = tokenize(text)
        unknown = [t for t in tokens if t not in vocabulary]
        out.append({
            "text": text,
            "expected": sentiment_label(gold),
            "expected_code": gold,
            "predicted": sentiment_label(result["label"]),
            "predicted_code": result["label"],
            "confidence": result["confidence"],
            "unknown_ratio": round(len(unknown) / len(tokens), 3) if tokens else 0.0,
        })
        if len(out) >= limit:
            break
    return out
