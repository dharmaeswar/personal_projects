package com.dharma.banking.dto;

import java.util.List;

/** One page of an account's transaction history, with the counts a caller needs to page through it. */
public class PagedTransactionsResponse {
    private final List<TransactionResponse> content;
    private final int page;
    private final int size;
    private final long totalElements;
    private final int totalPages;

    public PagedTransactionsResponse(List<TransactionResponse> content, int page, int size,
            long totalElements, int totalPages) {
        this.content = content;
        this.page = page;
        this.size = size;
        this.totalElements = totalElements;
        this.totalPages = totalPages;
    }

    public List<TransactionResponse> getContent() { return content; }
    public int getPage() { return page; }
    public int getSize() { return size; }
    public long getTotalElements() { return totalElements; }
    public int getTotalPages() { return totalPages; }
}
