package com.dharma.mortgage.controller;

import com.dharma.mortgage.dto.ApplicationResponse;
import com.dharma.mortgage.dto.CreateApplicationRequest;
import com.dharma.mortgage.dto.FunnelMetricsResponse;
import com.dharma.mortgage.service.ApplicationService;
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
@RequestMapping("/api/applications")
public class ApplicationController {
    private final ApplicationService service;

    public ApplicationController(ApplicationService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ApplicationResponse create(@Valid @RequestBody CreateApplicationRequest request) {
        return service.createApplication(request);
    }

    @GetMapping
    public List<ApplicationResponse> list() {
        return service.listApplications();
    }

    @GetMapping("/funnel")
    public FunnelMetricsResponse funnel() {
        return service.funnelMetrics();
    }

    @GetMapping("/{id}")
    public ApplicationResponse get(@PathVariable String id) {
        return service.getApplication(id);
    }

    @PostMapping("/{id}/submit")
    public ApplicationResponse submit(@PathVariable String id) {
        return service.submitApplication(id);
    }

    @PostMapping("/{id}/decide")
    public ApplicationResponse decide(@PathVariable String id) {
        return service.decideApplication(id);
    }

    @PostMapping("/{id}/closing")
    public ApplicationResponse startClosing(@PathVariable String id) {
        return service.startClosing(id);
    }

    @PostMapping("/{id}/closing/{item}")
    public ApplicationResponse completeClosingItem(@PathVariable String id,
            @PathVariable String item) {
        return service.completeClosingItem(id, item);
    }

    @PostMapping("/{id}/fund")
    public ApplicationResponse fund(@PathVariable String id) {
        return service.fundApplication(id);
    }
}
