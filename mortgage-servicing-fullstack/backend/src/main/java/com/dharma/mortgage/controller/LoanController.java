package com.dharma.mortgage.controller;

import com.dharma.mortgage.dto.AmortizationEntryResponse;
import com.dharma.mortgage.dto.CreateLoanRequest;
import com.dharma.mortgage.dto.LoanResponse;
import com.dharma.mortgage.dto.PaymentRequest;
import com.dharma.mortgage.dto.PaymentResponse;
import com.dharma.mortgage.service.LoanService;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/loans")
public class LoanController {
    private final LoanService service;

    public LoanController(LoanService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public LoanResponse create(@Valid @RequestBody CreateLoanRequest request) {
        return service.createLoan(request);
    }

    @GetMapping
    public List<LoanResponse> list() {
        return service.listLoans();
    }

    @GetMapping("/{id}")
    public LoanResponse get(@PathVariable String id) {
        return service.getLoan(id);
    }

    @PostMapping("/{id}/payments")
    public PaymentResponse pay(@PathVariable String id, @Valid @RequestBody PaymentRequest request) {
        return service.applyPayment(id, request);
    }

    @GetMapping("/{id}/payments")
    public List<PaymentResponse> payments(@PathVariable String id) {
        return service.paymentHistory(id);
    }

    @GetMapping("/{id}/schedule")
    public List<AmortizationEntryResponse> schedule(@PathVariable String id) {
        return service.amortizationSchedule(id);
    }

    @GetMapping("/{id}/escrow")
    public LoanService.EscrowSummary escrow(@PathVariable String id) {
        return service.escrow(id);
    }

    @GetMapping("/{id}/delinquency")
    public DelinquencyResponse delinquency(
            @PathVariable String id,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate asOf) {
        return new DelinquencyResponse(service.isDelinquent(id, asOf));
    }

    public record DelinquencyResponse(boolean delinquent) {}
}
