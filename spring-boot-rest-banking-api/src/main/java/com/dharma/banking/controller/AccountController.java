package com.dharma.banking.controller;

import com.dharma.banking.dto.AccountResponse;
import com.dharma.banking.dto.CreateAccountRequest;
import com.dharma.banking.dto.MoneyRequest;
import com.dharma.banking.dto.TransactionResponse;
import com.dharma.banking.dto.TransferRequest;
import com.dharma.banking.service.AccountService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {
    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AccountResponse create(@Valid @RequestBody CreateAccountRequest request) {
        return service.createAccount(request);
    }

    @GetMapping
    public List<AccountResponse> list() {
        return service.listAccounts();
    }

    @GetMapping("/{id}")
    public AccountResponse get(@PathVariable String id) {
        return service.getAccount(id);
    }

    @PostMapping("/{id}/deposit")
    public AccountResponse deposit(@PathVariable String id, @Valid @RequestBody MoneyRequest request) {
        return service.deposit(id, request.getAmount(), request.getMemo());
    }

    @PostMapping("/{id}/withdraw")
    public AccountResponse withdraw(@PathVariable String id, @Valid @RequestBody MoneyRequest request) {
        return service.withdraw(id, request.getAmount(), request.getMemo());
    }

    @PostMapping("/{id}/transfer")
    public AccountResponse transfer(@PathVariable String id, @Valid @RequestBody TransferRequest request) {
        return service.transfer(id, request);
    }

    @GetMapping("/{id}/transactions")
    public List<TransactionResponse> transactions(@PathVariable String id) {
        return service.transactionHistory(id);
    }
}
