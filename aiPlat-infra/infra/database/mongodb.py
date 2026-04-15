from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from .base import DatabaseClient
from .pool import ConnectionPool
from .schemas import DatabaseConfig, PoolStats


class MongoConnectionPool(ConnectionPool):
    def __init__(self, config: DatabaseConfig):
        self.config = config
        pool_config = config.pool
        self._client = None
        self._min_size = pool_config.min_size if pool_config else 5
        self._max_size = pool_config.max_size if pool_config else 20

    async def _get_client(self):
        if self._client is None:
            from motor.motor_asyncio import AsyncIOMotorClient
            
            # 构建MongoDB连接URL
            if self.config.user and self.config.password:
                # 带认证的连接
                connection_url = f"mongodb://{self.config.user}:{self.config.password}@{self.config.host}:{self.config.port}"
            else:
                # 无认证连接
                connection_url = f"mongodb://{self.config.host}:{self.config.port}"
            
            self._client = AsyncIOMotorClient(
                connection_url,
                maxPoolSize=self._max_size,
                minPoolSize=self._min_size,
            )
        return self._client

    async def acquire(self):
        return await self._get_client()

    async def release(self, conn):
        pass

    def get_stats(self) -> PoolStats:
        return PoolStats()

    async def resize(self, min_size: int, max_size: int) -> None:
        self._min_size = min_size
        self._max_size = max_size

    async def close(self):
        if self._client:
            self._client.close()


class MongoClient(DatabaseClient):
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[MongoConnectionPool] = None
        self._client = None
        self._session = None

    async def connect(self):
        self._pool = MongoConnectionPool(self.config)
        self._client = await self._pool.acquire()

    async def _get_client(self):
        if self._client is None:
            from motor.motor_asyncio import AsyncIOMotorClient
            
            # 构建MongoDB连接URL
            if self.config.user and self.config.password:
                # 带认证的连接
                connection_url = f"mongodb://{self.config.user}:{self.config.password}@{self.config.host}:{self.config.port}"
            else:
                # 无认证连接
                connection_url = f"mongodb://{self.config.host}:{self.config.port}"
            
            self._client = AsyncIOMotorClient(connection_url)
        return self._client

    def _get_database_and_collection(self, params: Dict):
        """获取数据库和集合对象"""
        client = self._client
        database_name = params.get("database", self.config.name)
        collection_name = params.get("collection")
        
        if not collection_name:
            raise ValueError("Missing 'collection' parameter")
        
        db = client[database_name]
        collection = db[collection_name]
        return collection

    async def execute(self, query: str, params: Dict = None) -> List[Dict]:
        """执行MongoDB操作
        
        Args:
            query: 操作类型，支持: find, find_one, insert_one, insert_many, 
                   update_one, update_many, delete_one, delete_many, aggregate, count
            params: 操作参数，必须包含collection，其他参数根据操作类型而定
                   find: {"collection": "users", "filter": {"age": {"$gt": 18}}}
                   insert_one: {"collection": "users", "document": {...}}
                   update_many: {"collection": "users", "filter": {...}, "update": {...}}
        
        Returns:
            查询操作返回文档列表，其他操作返回操作结果
        """
        params = params or {}
        collection = self._get_database_and_collection(params)
        
        session = self._session
        operation = query.lower()
        
        try:
            if operation == "find":
                filter_dict = params.get("filter", {})
                projection = params.get("projection")
                sort = params.get("sort")
                limit = params.get("limit", 0)
                skip = params.get("skip", 0)
                
                cursor = collection.find(filter_dict, projection, session=session)
                
                if sort:
                    cursor = cursor.sort(sort)
                if skip:
                    cursor = cursor.skip(skip)
                if limit:
                    cursor = cursor.limit(limit)
                
                results = await cursor.to_list(length=None)
                return [self._bson_to_dict(doc) for doc in results]
            
            elif operation == "find_one":
                filter_dict = params.get("filter", {})
                projection = params.get("projection")
                doc = await collection.find_one(filter_dict, projection, session=session)
                return [self._bson_to_dict(doc)] if doc else []
            
            elif operation == "insert_one":
                document = params.get("document")
                if not document:
                    raise ValueError("Missing 'document' parameter for insert_one")
                result = await collection.insert_one(document, session=session)
                return [{"inserted_id": str(result.inserted_id), "acknowledged": result.acknowledged}]
            
            elif operation == "insert_many":
                documents = params.get("documents", [])
                if not documents:
                    raise ValueError("Missing 'documents' parameter for insert_many")
                result = await collection.insert_many(documents, session=session)
                return [{"inserted_ids": [str(id) for id in result.inserted_ids], "acknowledged": result.acknowledged}]
            
            elif operation == "update_one":
                filter_dict = params.get("filter", {})
                update_dict = params.get("update")
                upsert = params.get("upsert", False)
                if not update_dict:
                    raise ValueError("Missing 'update' parameter for update_one")
                result = await collection.update_one(filter_dict, update_dict, upsert=upsert, session=session)
                return [{"matched_count": result.matched_count, "modified_count": result.modified_count, 
                        "upserted_id": str(result.upserted_id) if result.upserted_id else None}]
            
            elif operation == "update_many":
                filter_dict = params.get("filter", {})
                update_dict = params.get("update")
                upsert = params.get("upsert", False)
                if not update_dict:
                    raise ValueError("Missing 'update' parameter for update_many")
                result = await collection.update_many(filter_dict, update_dict, upsert=upsert, session=session)
                return [{"matched_count": result.matched_count, "modified_count": result.modified_count,
                        "upserted_id": str(result.upserted_id) if result.upserted_id else None}]
            
            elif operation == "delete_one":
                filter_dict = params.get("filter", {})
                result = await collection.delete_one(filter_dict, session=session)
                return [{"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}]
            
            elif operation == "delete_many":
                filter_dict = params.get("filter", {})
                result = await collection.delete_many(filter_dict, session=session)
                return [{"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}]
            
            elif operation == "aggregate":
                pipeline = params.get("pipeline", [])
                cursor = collection.aggregate(pipeline, session=session)
                results = await cursor.to_list(length=None)
                return [self._bson_to_dict(doc) for doc in results]
            
            elif operation == "count":
                filter_dict = params.get("filter", {})
                count = await collection.count_documents(filter_dict, session=session)
                return [{"count": count}]
            
            elif operation == "distinct":
                field = params.get("field")
                filter_dict = params.get("filter", {})
                results = await collection.distinct(field, filter_dict, session=session)
                return [{"values": results}]
            
            else:
                raise ValueError(f"Unsupported operation: {query}")
        
        except Exception as e:
            raise RuntimeError(f"MongoDB operation failed: {str(e)}")

    async def execute_one(self, query: str, params: Dict = None) -> Optional[Dict]:
        """执行单个文档操作
        
        Args:
            query: 操作类型，通常为find_one
            params: 操作参数
        
        Returns:
            单个文档字典或None
        """
        params = params or {}
        collection = self._get_database_and_collection(params)
        session = self._session
        operation = query.lower()
        
        try:
            if operation in ["find", "find_one"]:
                filter_dict = params.get("filter", {})
                projection = params.get("projection")
                doc = await collection.find_one(filter_dict, projection, session=session)
                return self._bson_to_dict(doc) if doc else None
            
            elif operation == "insert_one":
                document = params.get("document")
                if not document:
                    raise ValueError("Missing 'document' parameter for insert_one")
                result = await collection.insert_one(document, session=session)
                return {"inserted_id": str(result.inserted_id), "acknowledged": result.acknowledged}
            
            elif operation == "update_one":
                filter_dict = params.get("filter", {})
                update_dict = params.get("update")
                upsert = params.get("upsert", False)
                if not update_dict:
                    raise ValueError("Missing 'update' parameter for update_one")
                result = await collection.update_one(filter_dict, update_dict, upsert=upsert, session=session)
                return {"matched_count": result.matched_count, "modified_count": result.modified_count,
                        "upserted_id": str(result.upserted_id) if result.upserted_id else None}
            
            elif operation == "delete_one":
                filter_dict = params.get("filter", {})
                result = await collection.delete_one(filter_dict, session=session)
                return {"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}
            
            elif operation == "count":
                filter_dict = params.get("filter", {})
                count = await collection.count_documents(filter_dict, session=session)
                return {"count": count}
            
            else:
                raise ValueError(f"Unsupported operation for execute_one: {query}")
        
        except Exception as e:
            raise RuntimeError(f"MongoDB operation failed: {str(e)}")

    async def execute_many(self, query: str, params_list: List[Dict]) -> List[Any]:
        """批量执行操作
        
        Args:
            query: 操作类型
            params_list: 参数列表，每个元素是一个操作参数字典
        
        Returns:
            操作结果列表
        """
        params = params_list[0] if params_list else {}
        collection = self._get_database_and_collection(params)
        session = self._session
        operation = query.lower()
        
        try:
            if operation == "insert":
                documents = params_list
                if not documents:
                    return []
                result = await collection.insert_many(documents, session=session)
                return [str(id) for id in result.inserted_ids]
            
            elif operation == "update":
                results = []
                for params in params_list:
                    filter_dict = params.get("filter", {})
                    update_dict = params.get("update")
                    upsert = params.get("upsert", False)
                    if not update_dict:
                        continue
                    result = await collection.update_many(filter_dict, update_dict, upsert=upsert, session=session)
                    results.append(result.modified_count)
                return results
            
            elif operation == "delete":
                results = []
                for params in params_list:
                    filter_dict = params.get("filter", {})
                    result = await collection.delete_many(filter_dict, session=session)
                    results.append(result.deleted_count)
                return results
            
            else:
                results = []
                for params in params_list:
                    result = await self.execute_one(query, params)
                    results.append(result)
                return results
        
        except Exception as e:
            raise RuntimeError(f"MongoDB batch operation failed: {str(e)}")

    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器
        
        MongoDB事务需要副本集支持
        """
        client = await self._get_client()
        async with await client.start_session() as session:
            async with session.start_transaction():
                try:
                    yield session
                except Exception:
                    await session.abort_transaction()
                    raise

    async def begin(self):
        """开始事务"""
        client = await self._get_client()
        self._session = await client.start_session()
        self._session.start_transaction()

    async def commit(self):
        """提交事务"""
        if self._session:
            await self._session.commit_transaction()
            await self._session.end_session()
            self._session = None

    async def rollback(self):
        """回滚事务"""
        if self._session:
            await self._session.abort_transaction()
            await self._session.end_session()
            self._session = None

    async def close(self):
        if self._session:
            await self._session.end_session()
            self._session = None
        if self._client:
            self._client.close()
        if self._pool:
            await self._pool.close()

    def is_connected(self) -> bool:
        return self._client is not None

    @property
    def pool(self) -> Optional[ConnectionPool]:
        return self._pool
    
    @staticmethod
    def _bson_to_dict(doc: Dict) -> Dict:
        """将BSON文档转换为字典，处理ObjectId等特殊类型"""
        if not doc:
            return doc
        
        result = {}
        for key, value in doc.items():
            if hasattr(value, '__dict__'):
                result[key] = str(value)
            else:
                result[key] = value
        
        if '_id' in result:
            result['_id'] = str(result['_id'])
        
        return result
