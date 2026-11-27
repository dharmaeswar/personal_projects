package com.dharma.mortgage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoanControllerTest {
    @Autowired
    private MockMvc mockMvc;

    private String createLoan() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/loans")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"borrowerName":"Test Borrower","originalPrincipal":300000,
                                 "annualRatePct":6.5,"termMonths":360,
                                 "startDate":"2026-01-01","escrowMonthly":250.00}"""))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.monthlyPayment").value(1896.20))
                .andReturn();
        String body = result.getResponse().getContentAsString();
        return body.split("\"id\":\"")[1].split("\"")[0];
    }

    @Test
    void createLoanReturnsMonthlyPayment() throws Exception {
        createLoan();
    }

    @Test
    void getUnknownLoanReturns404() throws Exception {
        mockMvc.perform(get("/api/loans/no-such-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Loan not found"));
    }

    @Test
    void paymentSplitsAndIsIdempotent() throws Exception {
        String id = createLoan();
        String body = """
                {"amount":2146.20,"paymentDate":"2026-02-01","idempotencyKey":"ctrl-1"}""";
        mockMvc.perform(post("/api/loans/" + id + "/payments")
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principalPortion").value(271.20))
                .andExpect(jsonPath("$.interestPortion").value(1625.00))
                .andExpect(jsonPath("$.escrowPortion").value(250.00));
        // Replay the same key: same payment, no second charge.
        mockMvc.perform(post("/api/loans/" + id + "/payments")
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/loans/" + id + "/payments"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)));
    }

    @Test
    void paymentBelowMinimumReturns422() throws Exception {
        String id = createLoan();
        mockMvc.perform(post("/api/loans/" + id + "/payments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"amount":100.00,"paymentDate":"2026-02-01"}"""))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error").value("Invalid payment"));
    }

    @Test
    void invalidLoanReturns400WithFieldErrors() throws Exception {
        mockMvc.perform(post("/api/loans")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"borrowerName":"Test Borrower","originalPrincipal":-5,
                                 "annualRatePct":6.5,"termMonths":360,
                                 "startDate":"2026-01-01","escrowMonthly":250.00}"""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.details[0]").value("originalPrincipal: originalPrincipal must be at least 1000.00"));
    }

    @Test
    void scheduleHas360RowsForAFreshLoan() throws Exception {
        String id = createLoan();
        mockMvc.perform(get("/api/loans/" + id + "/schedule"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(360)))
                .andExpect(jsonPath("$[0].interest").value(1625.00))
                .andExpect(jsonPath("$[359].remainingBalance").value(0.00));
    }

    @Test
    void escrowEndpointReportsBalance() throws Exception {
        String id = createLoan();
        mockMvc.perform(get("/api/loans/" + id + "/escrow"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.escrowMonthly").value(250.00))
                .andExpect(jsonPath("$.escrowBalance").value(0.00));
    }
}
