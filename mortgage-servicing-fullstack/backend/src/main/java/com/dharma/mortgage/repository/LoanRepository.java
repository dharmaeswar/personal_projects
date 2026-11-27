package com.dharma.mortgage.repository;

import com.dharma.mortgage.model.Loan;
import java.util.List;
import java.util.Optional;

/** Storage contract for loans. The in-memory implementation keeps this demo
 *  self-contained; swap in a Spring Data JPA repository backed by the PostgreSQL
 *  DDL in src/main/resources/schema.sql without touching the service. */
public interface LoanRepository {
    Loan save(Loan loan);
    Optional<Loan> findById(String id);
    List<Loan> findAll();
}
