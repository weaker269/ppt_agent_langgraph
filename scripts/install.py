from sentence_transformers import SentenceTransformer

# 只保留你想要下载的模型名称
model_name = "shibing624/text2vec-base-chinese"

print(f"Downloading {model_name} ...")
SentenceTransformer(model_name, device="cpu")

print(f"--- ✅ {model_name} 下载完成 ---")

# 下面的代码已被移除，因为它们是用来下载 BAAI reranker 模型的
# from transformers import AutoModelForSequenceClassification, AutoTokenizer
# rerank = "BAAI/bge-reranker-large"
# AutoTokenizer.from_pretrained(rerank)
# AutoModelForSequenceClassification.from_pretrained(rerank)