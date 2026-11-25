import { useMemo, useState } from 'react';

export function usePagination<T>(items: T[], pageSize = 10) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(pageSize);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / size) || 1);
  const safePage = Math.min(Math.max(page, 1), totalPages);

  const pageItems = useMemo(() => {
    const start = (safePage - 1) * size;
    return items.slice(start, start + size);
  }, [items, safePage, size]);

  function goTo(next: number) {
    setPage(Math.min(Math.max(next, 1), totalPages));
  }

  function changeSize(next: number) {
    setSize(next);
    setPage(1);
  }

  function reset() {
    setPage(1);
  }

  return {
    page: safePage,
    pageSize: size,
    total,
    totalPages,
    pageItems,
    setPage: goTo,
    setPageSize: changeSize,
    reset,
    from: total === 0 ? 0 : (safePage - 1) * size + 1,
    to: Math.min(safePage * size, total),
  };
}
