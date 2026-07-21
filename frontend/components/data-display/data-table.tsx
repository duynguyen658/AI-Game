"use client";

import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

export function DataTable<T>({ data, columns, label }: { data: T[]; columns: ColumnDef<T>[]; label: string }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  // TanStack Table intentionally returns stateful callbacks that React Compiler skips.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  return (
    <div className="overflow-x-auto border-y bg-white">
      <table className="w-full min-w-[760px] border-collapse text-left text-sm" aria-label={label}>
        <thead className="bg-[var(--surface-muted)] text-xs text-[var(--muted)]">
          {table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th className="h-10 border-b px-3 font-semibold" key={header.id}>{header.isPlaceholder ? null : header.column.getCanSort() ? <Button variant="ghost" size="sm" className="-ml-2" onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}{header.column.getIsSorted() === "asc" ? <ArrowUp className="size-3" /> : header.column.getIsSorted() === "desc" ? <ArrowDown className="size-3" /> : <ChevronsUpDown className="size-3 opacity-55" />}</Button> : flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}
        </thead>
        <tbody>{table.getRowModel().rows.map((row) => <tr className="border-b last:border-b-0 hover:bg-[var(--surface-muted)]/55" key={row.id}>{row.getVisibleCells().map((cell) => <td className="h-11 px-3 align-middle" key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
