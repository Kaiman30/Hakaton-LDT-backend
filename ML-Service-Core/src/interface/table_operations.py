"""
Module containing functions that call the needed table interface operations
using async database connectors.
"""
import asyncio
from typing import Any, Dict, List, Optional
from connectors.async_db_connector import AsyncPostgreSQLConnector, call_table_interface


async def execute_query(
    connector: AsyncPostgreSQLConnector, 
    query: str, 
    *args
) -> str:
    """
    Execute a query using the connector's execute method
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        query: SQL query to execute
        *args: Query parameters
        
    Returns:
        Result of the query execution
    """
    operation_func = call_table_interface(connector, 'execute')
    return await operation_func(query, *args)


async def load_data(
    connector: AsyncPostgreSQLConnector, 
    query: str, 
    *args
) -> List[Dict[str, Any]]:
    """
    Load data from database using the connector's load method
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        query: SQL SELECT query
        *args: Query parameters
        
    Returns:
        List of result rows as dictionaries
    """
    operation_func = call_table_interface(connector, 'load')
    return await operation_func(query, *args)


async def load_single_row(
    connector: AsyncPostgreSQLConnector, 
    query: str, 
    *args
) -> Optional[Dict[str, Any]]:
    """
    Load a single row from database
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        query: SQL SELECT query
        *args: Query parameters
        
    Returns:
        Single result row as dictionary or None
    """
    operation_func = call_table_interface(connector, 'load_one')
    return await operation_func(query, *args)


async def load_scalar_value(
    connector: AsyncPostgreSQLConnector, 
    query: str, 
    *args
) -> Any:
    """
    Load a single scalar value from database
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        query: SQL SELECT query
        *args: Query parameters
        
    Returns:
        Single scalar value
    """
    operation_func = call_table_interface(connector, 'load_scalar')
    return await operation_func(query, *args)


async def execute_batch(
    connector: AsyncPostgreSQLConnector, 
    query: str, 
    args_list: List[tuple]
) -> str:
    """
    Execute a query multiple times with different parameters
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        query: SQL query to execute
        args_list: List of parameter tuples
        
    Returns:
        Result of the batch execution
    """
    operation_func = call_table_interface(connector, 'execute_many')
    return await operation_func(query, args_list)


async def load_concurrent_queries(
    connector: AsyncPostgreSQLConnector, 
    queries: List[tuple]
) -> List[List[Dict[str, Any]]]:
    """
    Execute multiple SELECT queries concurrently
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        queries: List of (query, *args) tuples
        
    Returns:
        List of result lists (one per query)
    """
    operation_func = call_table_interface(connector, 'load_concurrent')
    return await operation_func(queries)


async def stream_large_result_set(
    connector: AsyncPostgreSQLConnector,
    query: str,
    *args,
    chunk_size: int = 1000
) -> List[Dict[str, Any]]:
    """
    Stream large result sets in chunks
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        query: SQL SELECT query
        *args: Query parameters
        chunk_size: Number of rows per chunk
        
    Returns:
        Generator yielding chunks of result rows
    """
    operation_func = call_table_interface(connector, 'load_stream')
    chunks = []
    async for chunk in operation_func(query, *args, chunk_size=chunk_size):
        chunks.append(chunk)
    return chunks


async def perform_bulk_insert(
    connector: AsyncPostgreSQLConnector,
    table: str,
    columns: List[str],
    rows: List[tuple],
    batch_size: int = 1000
) -> int:
    """
    Perform bulk insert with batching
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        table: Table name
        columns: Column names
        rows: List of row tuples
        batch_size: Number of rows per batch
        
    Returns:
        Total number of inserted rows
    """
    operation_func = call_table_interface(connector, 'bulk_insert')
    return await operation_func(table, columns, rows, batch_size=batch_size)


async def check_database_health(
    connector: AsyncPostgreSQLConnector
) -> bool:
    """
    Check database connectivity and health
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        
    Returns:
        True if healthy, False otherwise
    """
    operation_func = call_table_interface(connector, 'health_check')
    return await operation_func()


async def get_connection_pool_stats(
    connector: AsyncPostgreSQLConnector
) -> Dict[str, Any]:
    """
    Get connection pool statistics
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        
    Returns:
        Dictionary with pool statistics
    """
    operation_func = call_table_interface(connector, 'get_pool_stats')
    return await operation_func()


# Convenience function to initialize and use a connector
async def with_db_connection(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    operation: str,
    *args,
    min_pool_size: int = 1,
    max_pool_size: int = 20,
    **kwargs
) -> Any:
    """
    Initialize a connector, perform an operation, and clean up
    
    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password
        operation: Name of the operation to perform
        *args: Arguments for the operation
        min_pool_size: Minimum pool size
        max_pool_size: Maximum pool size
        **kwargs: Keyword arguments for the operation
        
    Returns:
        Result of the operation
    """
    connector = AsyncPostgreSQLConnector(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size
    )
    
    try:
        await connector.initialize()
        operation_func = call_table_interface(connector, operation)
        if kwargs:
            return await operation_func(*args, **kwargs)
        else:
            return await operation_func(*args)
    finally:
        await connector.shutdown()


# Specific table operations
async def create_table_if_not_exists(
    connector: AsyncPostgreSQLConnector,
    table_name: str,
    schema: str  # SQL schema definition
) -> str:
    """
    Create a table if it doesn't exist
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        table_name: Name of the table to create
        schema: SQL schema definition for the table
        
    Returns:
        Result of the CREATE TABLE operation
    """
    query = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"
    return await execute_query(connector, query)


async def insert_record(
    connector: AsyncPostgreSQLConnector,
    table: str,
    columns: List[str],
    values: tuple
) -> str:
    """
    Insert a single record into a table
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        table: Table name
        columns: Column names
        values: Values to insert
        
    Returns:
        Result of the INSERT operation
    """
    placeholders = ', '.join([f'${i+1}' for i in range(len(values))])
    column_names = ', '.join(columns)
    query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
    return await execute_query(connector, query, *values)


async def select_all_from_table(
    connector: AsyncPostgreSQLConnector,
    table: str,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Select all records from a table
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        table: Table name
        limit: Optional limit on number of records
        
    Returns:
        List of all records as dictionaries
    """
    query = f"SELECT * FROM {table}"
    if limit:
        query += f" LIMIT ${len([limit])}"  # Actually just: LIMIT $1
        return await load_data(connector, query, limit)
    else:
        return await load_data(connector, query)


async def update_records(
    connector: AsyncPostgreSQLConnector,
    table: str,
    set_clause: str,  # SET column1 = $1, column2 = $2, ...
    where_clause: str,  # WHERE condition with placeholders
    *args  # Parameters for both SET and WHERE clauses
) -> str:
    """
    Update records in a table
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        table: Table name
        set_clause: SET clause with placeholders
        where_clause: WHERE clause with placeholders
        *args: Parameters for the query
        
    Returns:
        Result of the UPDATE operation
    """
    query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
    return await execute_query(connector, query, *args)


async def delete_records(
    connector: AsyncPostgreSQLConnector,
    table: str,
    where_clause: str,  # WHERE condition with placeholders
    *args  # Parameters for the WHERE clause
) -> str:
    """
    Delete records from a table
    
    Args:
        connector: AsyncPostgreSQLConnector instance
        table: Table name
        where_clause: WHERE clause with placeholders
        *args: Parameters for the query
        
    Returns:
        Result of the DELETE operation
    """
    query = f"DELETE FROM {table} WHERE {where_clause}"
    return await execute_query(connector, query, *args)