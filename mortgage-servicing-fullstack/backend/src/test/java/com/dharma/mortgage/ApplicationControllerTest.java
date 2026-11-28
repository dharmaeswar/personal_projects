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
class ApplicationControllerTest {
    @Autowired
    private MockMvc mockMvc;

    private static final String STRONG_APPLICATION = """
            {"borrowerName":"Test Borrower","requestedAmount":300000,
             "homeValue":400000,"annualIncome":120000,"monthlyDebts":3000,
             "creditScore":720}""";

    private String createApplication() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/applications")
                        .contentType(MediaType.APPLICATION_JSON).content(STRONG_APPLICATION))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("STARTED"))
                .andExpect(jsonPath("$.loanToValue").value(0.75))
                .andExpect(jsonPath("$.debtToIncome").value(0.30))
                .andReturn();
        String body = result.getResponse().getContentAsString();
        return body.split("\"id\":\"")[1].split("\"")[0];
    }

    @Test
    void fullFunnelThroughTheApi() throws Exception {
        String id = createApplication();
        mockMvc.perform(post("/api/applications/" + id + "/submit"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUBMITTED"));
        mockMvc.perform(post("/api/applications/" + id + "/decide"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"))
                .andExpect(jsonPath("$.decision").value("APPROVED"));
        mockMvc.perform(post("/api/applications/" + id + "/closing"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("CLOSING"));
        // Funding is blocked while the checklist is open.
        mockMvc.perform(post("/api/applications/" + id + "/fund"))
                .andExpect(status().isConflict());
        for (String item : new String[]{"APPRAISAL", "TITLE_SEARCH",
                "HOMEOWNERS_INSURANCE", "FINAL_DISCLOSURE"}) {
            mockMvc.perform(post("/api/applications/" + id + "/closing/" + item))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.closingChecklist." + item).value(true));
        }
        mockMvc.perform(post("/api/applications/" + id + "/fund"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("FUNDED"));
    }

    @Test
    void deniedApplicationShowsReasons() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/applications")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"borrowerName":"Test Borrower","requestedAmount":380000,
                                 "homeValue":400000,"annualIncome":120000,"monthlyDebts":3000,
                                 "creditScore":600}"""))
                .andExpect(status().isCreated())
                .andReturn();
        String id = result.getResponse().getContentAsString().split("\"id\":\"")[1].split("\"")[0];
        mockMvc.perform(post("/api/applications/" + id + "/submit"))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/applications/" + id + "/decide"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DENIED"))
                .andExpect(jsonPath("$.decisionReasons", hasSize(2)));
    }

    @Test
    void outOfOrderTransitionReturns409() throws Exception {
        String id = createApplication();
        mockMvc.perform(post("/api/applications/" + id + "/decide"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("Invalid application state"));
    }

    @Test
    void getUnknownApplicationReturns404() throws Exception {
        mockMvc.perform(get("/api/applications/no-such-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Application not found"));
    }

    @Test
    void invalidApplicationReturns400() throws Exception {
        mockMvc.perform(post("/api/applications")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"borrowerName":"Test Borrower","requestedAmount":300000,
                                 "homeValue":400000,"annualIncome":120000,"monthlyDebts":3000,
                                 "creditScore":299}"""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("Validation failed"));
    }

    @Test
    void funnelEndpointReportsCounts() throws Exception {
        // The in-memory store is shared across tests in this class, so assert
        // the funnel moves by exactly one application instead of an absolute total.
        MvcResult before = mockMvc.perform(get("/api/applications/funnel"))
                .andExpect(status().isOk()).andReturn();
        int totalBefore = Integer.parseInt(before.getResponse().getContentAsString()
                .split("\"total\":")[1].split(",")[0]);
        createApplication();
        mockMvc.perform(get("/api/applications/funnel"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(totalBefore + 1));
    }
}
