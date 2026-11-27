package com.dharma.banking;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AccountControllerTest {
    @Autowired
    private MockMvc mockMvc;

    private String createAccount(String owner, String type, String balance) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"ownerName\":\"" + owner + "\",\"accountType\":\""
                                + type + "\",\"openingBalance\":" + balance + "}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.balance", is(Double.parseDouble(balance))))
                .andReturn();
        String body = result.getResponse().getContentAsString();
        return body.split("\"id\":\"")[1].split("\"")[0];
    }

    @Test
    void createAndGetAccount() throws Exception {
        String id = createAccount("Ada Lovelace", "CHECKING", "100.00");
        mockMvc.perform(get("/api/accounts/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerName", is("Ada Lovelace")))
                .andExpect(jsonPath("$.accountType", is("CHECKING")));
    }

    @Test
    void depositWithdrawAndHistoryFlow() throws Exception {
        String id = createAccount("Grace Hopper", "SAVINGS", "50.00");
        mockMvc.perform(post("/api/accounts/" + id + "/deposit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"amount\":25.00,\"memo\":\"Paycheck\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.balance", is(75.0)));
        mockMvc.perform(post("/api/accounts/" + id + "/withdraw")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"amount\":10.00}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.balance", is(65.0)));
        mockMvc.perform(get("/api/accounts/" + id + "/transactions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(3)));
    }

    @Test
    void transferBetweenAccounts() throws Exception {
        String from = createAccount("Ada Lovelace", "CHECKING", "200.00");
        String to = createAccount("Grace Hopper", "SAVINGS", "0.00");
        mockMvc.perform(post("/api/accounts/" + from + "/transfer")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"toAccountId\":\"" + to
                                + "\",\"amount\":60.00,\"idempotencyKey\":\"web-1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.balance", is(140.0)));
        mockMvc.perform(get("/api/accounts/" + to))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.balance", is(60.0)));
    }

    @Test
    void overdraftReturns422WithErrorBody() throws Exception {
        String id = createAccount("Ada Lovelace", "CHECKING", "10.00");
        mockMvc.perform(post("/api/accounts/" + id + "/withdraw")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"amount\":11.00}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error", is("Insufficient funds")));
    }

    @Test
    void unknownAccountReturns404() throws Exception {
        mockMvc.perform(get("/api/accounts/does-not-exist"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error", is("Account not found")));
    }

    @Test
    void invalidCreateRequestReturns400WithFieldErrors() throws Exception {
        mockMvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"ownerName\":\"\",\"accountType\":\"BROKERAGE\",\"openingBalance\":-5}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("Validation failed")))
                .andExpect(jsonPath("$.details", hasSize(3)));
    }

    @Test
    void negativeDepositIsRejectedByValidation() throws Exception {
        String id = createAccount("Ada Lovelace", "CHECKING", "10.00");
        mockMvc.perform(post("/api/accounts/" + id + "/deposit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"amount\":0}"))
                .andExpect(status().isBadRequest());
    }
}
