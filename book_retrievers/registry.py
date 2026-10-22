"""按书名分派到各自检索逻辑；未知书名直接报错，避免静默套用别书规则。"""

from . import ditian_sui, qiong_tong_bao_jian, sanming_tonghui, ziping_zhenquan

RETRIEVERS = {
    "穷通宝鉴": qiong_tong_bao_jian,
    "三命通会": sanming_tonghui,
    "子平真诠": ziping_zhenquan,
    "滴天髓": ditian_sui,
}


def retrieve(book_name: str, chart: dict, topic: str, count: int, collection, rag_module) -> dict:
    retriever = RETRIEVERS.get(book_name)
    if retriever is None:
        raise ValueError(f"尚未为《{book_name}》配置独立检索器")
    if book_name == "穷通宝鉴":
        return retriever.retrieve(topic, chart["检索条件"], count, collection, rag_module)
    return retriever.retrieve(chart, topic, count, collection)
