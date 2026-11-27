package com.dharma.banking;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.dharma.banking.dto.AccountResponse;
import com.dharma.banking.dto.CreateAccountRequest;
import com.dharma.banking.dto.TransactionResponse;
import com.dharma.banking.dto.TransferRequest;
import com.dharma.banking.repository.InMemoryAccountRepository;
import com.dharma.banking.service.AccountNotFoundException;
import com.dharma.banking.service.AccountService;
import com.dharma.banking.service.InsufficientFundsException;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AccountServiceTest {
    private AccountService service;

    @BeforeEach
    void setUp() {
        service = new AccountService(new InMemoryAccountRepository());
    }

    private AccountResponse create(String owner, String type, String balance) {
        CreateAccountRequest request = new CreateAccountRequest();
        request.setOwnerName(owner);
        request.setAccountType(type);
        request.setOpeningBalance(new BigDecimal(balance));
        return service.createAccount(request);
    }

    private TransferRequest transfer(String toId, String amount, String key) {
        TransferRequest request = new TransferRequest();
        request.setToAccountId(toId);
        request.setAmount(new BigDecimal(amount));
        request.setIdempotencyKey(key);
        return request;
    }

    @Test
    void createAccountRecordsOpeningBalanceAsDeposit() {
        AccountResponse account = create("Ada Lovelace", "CHECKING", "250.00");
        assertEquals(new BigDecimal("250.00"), account.getBalance());
        List<TransactionResponse> history = service.transactionHistory(account.getId());
        assertEquals(1, history.size());
        assertEquals("DEPOSIT", history.get(0).getType());
    }

    @Test
    void createAccountWithZeroBalanceHasNoTransactions() {
        AccountResponse account = create("Grace Hopper", "SAVINGS", "0.00");
        assertEquals(new BigDecimal("0.00"), account.getBalance());
        assertTrue(service.transactionHistory(account.getId()).isEmpty());
    }

    @Test
    void depositAddsToBalanceAndRecordsTransaction() {
        AccountResponse account = create("Ada Lovelace", "CHECKING", "100.00");
        AccountResponse updated = service.deposit(account.getId(), new BigDecimal("50.25"), "Paycheck");
        assertEquals(new BigDecimal("150.25"), updated.getBalance());
        assertEquals(2, service.transactionHistory(account.getId()).size());
    }

    @Test
    void withdrawSubtractsAndRejectsOverdraft() {
        AccountResponse account = create("Ada Lovelace", "CHECKING", "100.00");
        AccountResponse updated = service.withdraw(account.getId(), new BigDecimal("40.00"), "ATM");
        assertEquals(new BigDecimal("60.00"), updated.getBalance());
        assertThrows(InsufficientFundsException.class,
                () -> service.withdraw(account.getId(), new BigDecimal("60.01"), "Too much"));
        // Failed withdrawal leaves the balance untouched.
        assertEquals(new BigDecimal("60.00"), service.getAccount(account.getId()).getBalance());
    }

    @Test
    void withdrawExactBalanceLeavesZero() {
        AccountResponse account = create("Ada Lovelace", "SAVINGS", "75.50");
        AccountResponse updated = service.withdraw(account.getId(), new BigDecimal("75.50"), "Close out");
        assertEquals(new BigDecimal("0.00"), updated.getBalance());
    }

    @Test
    void transferMovesMoneyBothWaysAndRecordsBothLegs() {
        AccountResponse from = create("Ada Lovelace", "CHECKING", "200.00");
        AccountResponse to = create("Grace Hopper", "SAVINGS", "50.00");
        service.transfer(from.getId(), transfer(to.getId(), "80.00", "t-1"));
        assertEquals(new BigDecimal("120.00"), service.getAccount(from.getId()).getBalance());
        assertEquals(new BigDecimal("130.00"), service.getAccount(to.getId()).getBalance());
        assertEquals("TRANSFER_OUT",
                service.transactionHistory(from.getId()).get(1).getType());
        assertEquals("TRANSFER_IN",
                service.transactionHistory(to.getId()).get(1).getType());
    }

    @Test
    void transferRejectsOverdraftAndSelfTransfer() {
        AccountResponse from = create("Ada Lovelace", "CHECKING", "30.00");
        AccountResponse to = create("Grace Hopper", "SAVINGS", "10.00");
        assertThrows(InsufficientFundsException.class,
                () -> service.transfer(from.getId(), transfer(to.getId(), "30.01", "t-2")));
        assertThrows(IllegalArgumentException.class,
                () -> service.transfer(from.getId(), transfer(from.getId(), "5.00", "t-3")));
        assertEquals(new BigDecimal("30.00"), service.getAccount(from.getId()).getBalance());
        assertEquals(new BigDecimal("10.00"), service.getAccount(to.getId()).getBalance());
    }

    @Test
    void duplicateIdempotencyKeyMovesMoneyOnlyOnce() {
        AccountResponse from = create("Ada Lovelace", "CHECKING", "200.00");
        AccountResponse to = create("Grace Hopper", "SAVINGS", "0.00");
        service.transfer(from.getId(), transfer(to.getId(), "25.00", "key-abc"));
        service.transfer(from.getId(), transfer(to.getId(), "25.00", "key-abc"));
        assertEquals(new BigDecimal("175.00"), service.getAccount(from.getId()).getBalance());
        assertEquals(new BigDecimal("25.00"), service.getAccount(to.getId()).getBalance());
    }

    @Test
    void unknownAccountThrowsNotFound() {
        assertThrows(AccountNotFoundException.class, () -> service.getAccount("no-such-id"));
        assertThrows(AccountNotFoundException.class,
                () -> service.deposit("no-such-id", new BigDecimal("1.00"), "x"));
    }

    @Test
    void concurrentDepositsDoNotLoseMoney() throws InterruptedException {
        AccountResponse account = create("Ada Lovelace", "CHECKING", "0.00");
        Thread[] threads = new Thread[20];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() ->
                    service.deposit(account.getId(), new BigDecimal("1.00"), "race"));
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }
        assertEquals(new BigDecimal("20.00"), service.getAccount(account.getId()).getBalance());
    }
}
