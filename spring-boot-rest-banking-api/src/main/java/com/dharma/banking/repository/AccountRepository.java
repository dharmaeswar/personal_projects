package com.dharma.banking.repository;

import com.dharma.banking.model.Account;
import java.util.List;
import java.util.Optional;

/** Storage contract for accounts. The in-memory implementation keeps this demo
 *  self-contained; swap in a Spring Data JPA repository without touching the service. */
public interface AccountRepository {
    Account save(Account account);
    Optional<Account> findById(String id);
    List<Account> findAll();
}
