import os
import json
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("ChromaDB未安装，请运行: pip install chromadb")


class ChromaVectorStore:
    """基于ChromaDB的向量存储"""

    def __init__(
        self,
        persist_directory: str = "chroma_db",
        collection_name: str = "table_docs",
        embedding_model: str = "default"
    ):
        """
        :param persist_directory: ChromaDB持久化目录
        :param collection_name: 集合名称
        :param embedding_model: 嵌入模型名称
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB未安装，请运行: pip install chromadb")

        self.persist_directory = persist_directory
        self.collection_name = collection_name

        # 初始化ChromaDB客户端（持久化模式）
        self.client = chromadb.PersistentClient(path=persist_directory)

        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Table documentation chunks"}
        )

        print(f"✅ ChromaDB已初始化: {persist_directory}")
        print(f"   集合: {collection_name}, 当前文档数: {self.collection.count()}")

    def add(
        self,
        document: str,
        metadata: Dict,
        doc_id: str,
        embedding: List[float] = None
    ):
        """
        添加文档到向量库

        :param document: 文档内容
        :param metadata: 元数据
        :param doc_id: 文档ID（唯一）
        :param embedding: 可选的预计算向量（如果为None，ChromaDB会自动计算）
        """
        # ChromaDB可以自动计算embedding，也可以手动提供
        add_kwargs = {
            "documents": [document],
            "metadatas": [metadata],
            "ids": [doc_id]
        }

        if embedding is not None:
            add_kwargs["embeddings"] = [embedding]

        self.collection.add(**add_kwargs)

    def add_batch(
        self,
        documents: List[str],
        metadatas: List[Dict],
        ids: List[str],
        embeddings: List[List[float]] = None
    ):
        """
        批量添加文档

        :param documents: 文档列表
        :param metadatas: 元数据列表
        :param ids: ID列表
        :param embeddings: 可选的预计算向量列表
        """
        add_kwargs = {
            "documents": documents,
            "metadatas": metadatas,
            "ids": ids
        }

        if embeddings is not None:
            add_kwargs["embeddings"] = embeddings

        self.collection.add(**add_kwargs)

    def search(
        self,
        query_text: str = None,
        query_embedding: List[float] = None,
        top_k: int = 5,
        filter_metadata: Dict = None
    ) -> List[Dict]:
        """
        向量相似度搜索

        :param query_text: 查询文本（ChromaDB会自动计算embedding）
        :param query_embedding: 预计算的查询向量
        :param top_k: 返回结果数量
        :param filter_metadata: 元数据过滤条件
        :return: 搜索结果列表
        """
        if query_text is None and query_embedding is None:
            raise ValueError("必须提供 query_text 或 query_embedding")

        # 构建查询参数
        query_kwargs = {
            "n_results": top_k
        }

        if query_text is not None:
            query_kwargs["query_texts"] = [query_text]
        elif query_embedding is not None:
            query_kwargs["query_embeddings"] = [query_embedding]

        if filter_metadata is not None:
            query_kwargs["where"] = filter_metadata

        # 执行查询
        results = self.collection.query(**query_kwargs)

        # 格式化结果
        formatted_results = []
        for i in range(len(results['ids'][0])):
            formatted_results.append({
                "id": results['ids'][0][i],
                "document": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i] if 'distances' in results else None,
                "similarity": 1.0 / (1.0 + results['distances'][0][i]) if 'distances' in results else None
            })

        return formatted_results

    def delete(self, doc_ids: List[str] = None, filter_metadata: Dict = None):
        """
        删除文档

        :param doc_ids: 要删除的文档ID列表
        :param filter_metadata: 过滤条件
        """
        if doc_ids:
            self.collection.delete(ids=doc_ids)
        elif filter_metadata:
            self.collection.delete(where=filter_metadata)

    def count(self) -> int:
        """获取文档总数"""
        return self.collection.count()

    def clear(self):
        """清空集合"""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"description": "Table documentation chunks"}
        )
        print(f"✅ 集合已清空: {self.collection_name}")

    def get_all(self, limit: int = 100) -> List[Dict]:
        """获取所有文档（用于调试）"""
        results = self.collection.get(limit=limit)

        all_docs = []
        for i in range(len(results['ids'])):
            all_docs.append({
                "id": results['ids'][i],
                "document": results['documents'][i],
                "metadata": results['metadatas'][i]
            })

        return all_docs


class ChunkSplitter:
    """文档分块器"""

    @staticmethod
    def split_by_sections(markdown_content: str, table_name: str) -> List[Dict]:
        """
        按Markdown章节分块

        :param markdown_content: Markdown内容
        :param table_name: 表名
        :return: chunks列表
        """
        chunks = []

        # 按二级标题分割
        sections = markdown_content.split("\n## ")

        for i, section in enumerate(sections):
            if i == 0:
                # 第一部分包含一级标题
                if section.startswith("#"):
                    lines = section.strip().split("\n")
                    title = lines[0].replace("# ", "")
                    content = "\n".join(lines[1:]) if len(lines) > 1 else ""
                    chunk_type = "description"
                else:
                    continue
            else:
                # 后续部分是各个章节
                lines = section.strip().split("\n")
                title = lines[0]
                content = "\n".join(lines[1:]) if len(lines) > 1 else ""

                # 判断chunk类型
                chunk_type = ChunkSplitter._classify_section(title)

            if content.strip():
                chunks.append({
                    "table_name": table_name,
                    "chunk_type": chunk_type,
                    "title": title,
                    "content": content.strip(),
                    "full_text": f"{title}\n{content.strip()}"
                })

        return chunks

    @staticmethod
    def _classify_section(title: str) -> str:
        """根据章节标题分类"""
        title_lower = title.lower()

        if "字段" in title or "field" in title_lower:
            return "fields"
        elif "关联" in title or "relationship" in title_lower:
            return "relationships"
        elif "索引" in title or "index" in title_lower:
            return "indexes"
        elif "业务" in title or "rule" in title_lower:
            return "business_rules"
        elif "sql" in title_lower or "示例" in title:
            return "sql_examples"
        else:
            return "description"


class RAGRetriever:
    """RAG检索器（基于ChromaDB）"""

    def __init__(
        self,
        persist_directory: str = "chroma_db",
        collection_name: str = "table_docs"
    ):
        """
        :param persist_directory: ChromaDB持久化目录
        :param collection_name: 集合名称
        """
        self.vector_store = ChromaVectorStore(
            persist_directory=persist_directory,
            collection_name=collection_name
        )

    def build_index(
        self,
        docs_dir: str = "table_docs",
        rebuild: bool = False
    ):
        """
        构建索引

        :param docs_dir: 文档目录
        :param rebuild: 是否重建索引
        """
        if not rebuild and self.vector_store.count() > 0:
            print(f"✅ 使用已有索引: {self.vector_store.count()} 个chunks")
            return

        if not os.path.exists(docs_dir):
            raise FileNotFoundError(f"文档目录不存在: {docs_dir}")

        print(f"🔨 开始构建索引，扫描目录: {docs_dir}")

        # 如果需要重建，先清空
        if rebuild:
            self.vector_store.clear()

        # 遍历所有markdown文件
        total_chunks = 0
        for filename in os.listdir(docs_dir):
            if not filename.endswith(".md"):
                continue

            table_name = filename.replace(".md", "")
            file_path = os.path.join(docs_dir, filename)

            with open(file_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()

            # 分块
            chunks = ChunkSplitter.split_by_sections(markdown_content, table_name)

            # 准备批量添加的数据
            documents = []
            metadatas = []
            ids = []

            for chunk in chunks:
                documents.append(chunk["full_text"])
                metadatas.append({
                    "table_name": chunk["table_name"],
                    "chunk_type": chunk["chunk_type"],
                    "title": chunk["title"]
                })
                ids.append(f"{table_name}_{chunk['chunk_type']}")

            # 批量添加到ChromaDB（ChromaDB会自动计算embedding）
            if documents:
                self.vector_store.add_batch(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                total_chunks += len(documents)
                print(f"   ✅ {table_name}: {len(documents)} 个chunks")

        print(f"\n✅ 索引构建完成，共 {total_chunks} 个chunks")

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = True,
        filter_by_tables: List[str] = None
    ) -> Dict:
        """
        检索相关表文档

        :param query: 查询文本
        :param top_k: 返回chunks数量
        :param rerank: 是否重排序
        :param filter_by_tables: 过滤特定表
        :return: 检索结果
        """
        if self.vector_store.count() == 0:
            raise Exception("向量库为空，请先调用 build_index() 构建索引")

        # 构建过滤条件
        filter_metadata = None
        if filter_by_tables:
            # ChromaDB的过滤语法：$in 操作符
            filter_metadata = {
                "table_name": {"$in": filter_by_tables}
            }

        # 1. 向量检索（ChromaDB自动计算query的embedding）
        raw_results = self.vector_store.search(
            query_text=query,
            top_k=top_k * 2,  # 先多取一些，用于重排序
            filter_metadata=filter_metadata
        )

        # 2. 重排序
        if rerank:
            results = self._rerank(raw_results, query)
        else:
            results = raw_results[:top_k]

        # 3. 聚合结果，定位到表
        matched_tables = self._aggregate_by_table(results)

        return {
            "query": query,
            "matched_tables": matched_tables,
            "relevant_chunks": results,
            "context_text": self._build_context_text(results)
        }

    def _rerank(self, results: List[Dict], query: str) -> List[Dict]:
        """
        重排序：考虑chunk类型优先级

        :param results: 原始检索结果
        :param query: 查询文本
        :return: 重排序后的结果
        """
        # 定义chunk类型权重
        type_weights = {
            "description": 1.2,
            "sql_examples": 1.0,
            "business_rules": 0.9,
            "fields": 0.8,
            "relationships": 0.7,
            "indexes": 0.6
        }

        # 计算加权分数
        for result in results:
            chunk_type = result["metadata"].get("chunk_type", "description")
            weight = type_weights.get(chunk_type, 0.5)
            # ChromaDB返回的是distance，转换为similarity
            similarity = result.get("similarity", 0.5)
            result["score"] = similarity * weight

        # 按分数排序
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)

        return sorted_results[:5]  # 返回top-5

    def _aggregate_by_table(self, results: List[Dict]) -> List[Dict]:
        """
        按表名聚合结果

        :param results: 检索结果
        :return: 表聚合结果
        """
        table_scores = defaultdict(float)
        table_chunks = defaultdict(list)

        for result in results:
            table_name = result["metadata"]["table_name"]
            table_scores[table_name] += result.get("score", result.get("similarity", 0))
            table_chunks[table_name].append(result)

        # 按得分排序
        sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)

        matched_tables = []
        for table_name, score in sorted_tables:
            matched_tables.append({
                "table_name": table_name,
                "relevance_score": score,
                "chunk_count": len(table_chunks[table_name]),
                "chunk_types": list(set([
                    r["metadata"]["chunk_type"] for r in table_chunks[table_name]
                ]))
            })

        return matched_tables

    def _build_context_text(self, results: List[Dict]) -> str:
        """
        构建上下文文本（用于prompt）

        :param results: 检索结果
        :return: 格式化的上下文字本
        """
        if not results:
            return ""

        context_parts = []

        # 按表分组
        table_groups = defaultdict(list)
        for result in results:
            table_name = result["metadata"]["table_name"]
            table_groups[table_name].append(result)

        for table_name, chunks in table_groups.items():
            context_parts.append(f"\n### 表: {table_name}\n")

            for chunk in chunks:
                chunk_type = chunk["metadata"]["chunk_type"]
                title = chunk["metadata"]["title"]
                content = chunk["document"]

                context_parts.append(f"**{title}**\n{content}\n")

        return "\n".join(context_parts)

    def get_stats(self) -> Dict:
        """获取索引统计信息"""
        total_docs = self.vector_store.count()
        all_docs = self.vector_store.get_all(limit=total_docs)

        # 统计表分布
        table_distribution = defaultdict(int)
        type_distribution = defaultdict(int)

        for doc in all_docs:
            metadata = doc["metadata"]
            table_distribution[metadata.get("table_name", "unknown")] += 1
            type_distribution[metadata.get("chunk_type", "unknown")] += 1

        return {
            "total_chunks": total_docs,
            "table_distribution": dict(table_distribution),
            "type_distribution": dict(type_distribution)
        }


def build_rag_index(
    docs_dir: str = "table_docs",
    persist_directory: str = "chroma_db",
    collection_name: str = "table_docs",
    rebuild: bool = False
):
    """
    便捷函数：构建RAG索引

    :param docs_dir: 文档目录
    :param persist_directory: ChromaDB持久化目录
    :param collection_name: 集合名称
    :param rebuild: 是否重建
    """
    retriever = RAGRetriever(
        persist_directory=persist_directory,
        collection_name=collection_name
    )
    retriever.build_index(docs_dir=docs_dir, rebuild=rebuild)
    return retriever


def retrieve_relevant_tables(
    query: str,
    persist_directory: str = "chroma_db",
    collection_name: str = "table_docs"
) -> Dict:
    """
    便捷函数：检索相关表

    :param query: 查询文本
    :param persist_directory: ChromaDB持久化目录
    :param collection_name: 集合名称
    :return: 检索结果
    """
    retriever = RAGRetriever(
        persist_directory=persist_directory,
        collection_name=collection_name
    )
    return retriever.retrieve(query)


if __name__ == "__main__":
    # 测试ChromaDB RAG检索
    print("=" * 80)
    print("测试 ChromaDB RAG 检索系统")
    print("=" * 80)

    # 1. 构建索引
    print("\n【步骤1】构建索引...")
    retriever = build_rag_index(rebuild=True)

    # 显示统计信息
    stats = retriever.get_stats()
    print(f"\n📊 索引统计:")
    print(f"   总chunks: {stats['total_chunks']}")
    print(f"   表分布: {json.dumps(stats['table_distribution'], ensure_ascii=False, indent=2)}")
    print(f"   类型分布: {json.dumps(stats['type_distribution'], ensure_ascii=False, indent=2)}")

    # 2. 测试检索
    print("\n【步骤2】测试检索...")
    test_queries = [
        "修改活动奖品概率",
        "生成邀请码",
        "查询活动信息"
    ]

    for query in test_queries:
        print(f"\n💬 查询: {query}")
        result = retriever.retrieve(query)

        print(f"匹配的表:")
        for table in result["matched_tables"]:
            print(f"  - {table['table_name']} (得分: {table['relevance_score']:.3f}, "
                  f"chunks: {table['chunk_count']})")