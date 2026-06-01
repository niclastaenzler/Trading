"""Quantitative research harness.

A methodically honest pipeline to *search for* and *evaluate* a statistical
trading edge — with no-lookahead features, walk-forward validation, significance
testing against random, and leverage analysis.

Submodules:
    datasets      - data loaders (current crypto via Binance, CSV, broker, and
                    controlled synthetic generators with known ground truth)
    features      - no-lookahead feature engineering (+ optional news/sentiment)
    models        - baseline / logistic / gradient boosting under one interface
    walkforward   - expanding-window walk-forward with an embargo gap
    edge_analysis - metrics, significance, random Monte-Carlo, leverage
    report        - assembles an honest YES/NO edge verdict
"""
