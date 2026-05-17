# Machine Learning Overview

## What is Machine Learning?

Machine learning (ML) is a branch of artificial intelligence that enables systems to
learn patterns from data and improve their performance on tasks without being explicitly
programmed for each scenario.

The three main paradigms are:

- **Supervised learning** — the model trains on labelled input-output pairs (e.g.
  classification, regression).
- **Unsupervised learning** — the model discovers hidden structure in unlabelled data
  (e.g. clustering, dimensionality reduction).
- **Reinforcement learning** — an agent learns by interacting with an environment and
  receiving reward signals.

---

## Key Algorithms

| Algorithm | Type | Common Use-Cases |
|-----------|------|-----------------|
| Linear Regression | Supervised | Price prediction |
| Decision Trees | Supervised | Classification, fraud detection |
| Random Forest | Supervised | Feature-rich tabular data |
| K-Means | Unsupervised | Customer segmentation |
| Neural Networks | Both | Image recognition, NLP |
| Gradient Boosting (XGBoost) | Supervised | Competitive ML, tabular data |

---

## Deep Learning

Deep learning uses **multi-layered neural networks** (deep nets) to learn hierarchical
representations of data.

Key architectures:
- **Convolutional Neural Networks (CNNs)** — image and video processing.
- **Recurrent Neural Networks (RNNs) / LSTMs** — sequential data, time series.
- **Transformers** — state-of-the-art for NLP; the basis of GPT, BERT, and similar models.

---

## Evaluation Metrics

For **classification** tasks:
- Accuracy, Precision, Recall, F1-score
- ROC-AUC

For **regression** tasks:
- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- R² (coefficient of determination)

---

## Overfitting and Regularisation

Overfitting occurs when a model memorises training data and performs poorly on unseen
data. Common mitigations:

1. **More data** — the most effective remedy.
2. **Dropout** — randomly zeroes activations during training.
3. **L1 / L2 regularisation** — penalises large weights.
4. **Early stopping** — halt training when validation loss stops decreasing.
5. **Data augmentation** — synthetically expand the training set.

---

## RAG and Large Language Models (LLMs)

**Retrieval-Augmented Generation (RAG)** combines a vector search engine with an LLM:

1. User submits a query.
2. Relevant document chunks are retrieved from a vector database.
3. The LLM generates an answer grounded in the retrieved context.

This reduces hallucinations and keeps answers up-to-date without fine-tuning.
