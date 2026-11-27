package com.dharma.banking.service;

import com.dharma.banking.dto.AccountResponse;
import com.dharma.banking.dto.CreateAccountRequest;
import com.dharma.banking.dto.TransactionResponse;
import com.dharma.banking.dto.TransferRequest;
import com.dharma.banking.model.Account;
import com.dharma.banking.model.TransactionType;
import com.dharma.banking.repository.AccountRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Account operations. Rules enforced here, not in the controller:
 * <ul>
 *   <li>Amounts are positive and use BigDecimal (scale 2); doubles are never used for money.</li>
 *   <li>A withdrawal or transfer that exceeds the balance is rejected — no overdraft.</li>
 *   <li>A transfer moves money under one lock ordering (by account id) so two accounts can
 *       never deadlock, and a repeated idempotency key replays the original result instead
 *       of moving money twice.</li>
 *   <li>Self-transfers are rejected.</li>
 * </ul>
 * Logging never includes account balances, owner names, or full account ids.
 */
@Service
public class AccountService {
    private static final Logger log = LoggerFactory.getLogger(AccountService.class);
    private final AccountRepository repository;
    /** idempotencyKey -> resulting source-account response, kept in memory for this demo. */
    private final Map<String, AccountResponse> transferResults = new ConcurrentHashMap<>();

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    public AccountResponse createAccount(CreateAccountRequest request) {
        Account account = new Account(request.getOwnerName(), request.getAccountType(),
                request.getOpeningBalance());
        repository.save(account);
        log.info("Account created type={}", request.getAccountType());
        return new AccountResponse(account);
    }

    public AccountResponse getAccount(String id) {
        return new AccountResponse(requireAccount(id));
    }

    public List<AccountResponse> listAccounts() {
        return repository.findAll().stream().map(AccountResponse::new).toList();
    }

    public AccountResponse deposit(String id, BigDecimal amount, String memo) {
        Account account = requireAccount(id);
        synchronized (account) {
            account.apply(TransactionType.DEPOSIT, amount, memo == null ? "Deposit" : memo);
        }
        log.info("Deposit applied");
        return new AccountResponse(account);
    }

    public AccountResponse withdraw(String id, BigDecimal amount, String memo) {
        Account account = requireAccount(id);
        synchronized (account) {
            if (account.getBalance().compareTo(amount) < 0) {
                throw new InsufficientFundsException(id, account.getBalance(), amount);
            }
            account.apply(TransactionType.WITHDRAWAL, amount.negate(), memo == null ? "Withdrawal" : memo);
        }
        log.info("Withdrawal applied");
        return new AccountResponse(account);
    }

    public AccountResponse transfer(String fromId, TransferRequest request) {
        if (request.getIdempotencyKey() != null
                && transferResults.containsKey(request.getIdempotencyKey())) {
            log.info("Duplicate transfer replayed from idempotency key");
            return transferResults.get(request.getIdempotencyKey());
        }
        if (fromId.equals(request.getToAccountId())) {
            throw new IllegalArgumentException("Cannot transfer to the same account");
        }
        Account from = requireAccount(fromId);
        Account to = requireAccount(request.getToAccountId());
        // Lock in id order so concurrent opposite-direction transfers cannot deadlock.
        Account first = from.getId().compareTo(to.getId()) < 0 ? from : to;
        Account second = first == from ? to : from;
        AccountResponse result;
        synchronized (first) {
            synchronized (second) {
                if (from.getBalance().compareTo(request.getAmount()) < 0) {
                    throw new InsufficientFundsException(fromId, from.getBalance(), request.getAmount());
                }
                from.apply(TransactionType.TRANSFER_OUT, request.getAmount().negate(), "Transfer out");
                to.apply(TransactionType.TRANSFER_IN, request.getAmount(), "Transfer in");
                result = new AccountResponse(from);
            }
        }
        if (request.getIdempotencyKey() != null) {
            transferResults.put(request.getIdempotencyKey(), result);
        }
        log.info("Transfer applied");
        return result;
    }

    public List<TransactionResponse> transactionHistory(String id) {
        return requireAccount(id).getTransactions().stream()
                .map(TransactionResponse::new).toList();
    }

    private Account requireAccount(String id) {
        return repository.findById(id).orElseThrow(() -> new AccountNotFoundException(id));
    }
}
