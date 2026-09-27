# cython_workers/Cython/fast_parser.pyx
# cython: language_level=3

# Импорт из C-заголовка
cdef extern from "../C/parser.h":
    int process_c_bytes(const char* data, int length)

cpdef dict c_fast_parse(bytes raw_bytes):
    cdef const char* c_data = raw_bytes
    cdef int length = len(raw_bytes)
    
    # Высокоскоростной вызов C-кода
    cdef int status = process_c_bytes(c_data, length)
    return {"status": status, "parsed": True}