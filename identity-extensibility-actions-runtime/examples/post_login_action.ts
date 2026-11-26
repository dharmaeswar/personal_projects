/**
 * Sample tenant Action, written the way Auth0 Actions are authored
 * (TypeScript, post-login trigger). This file is a fixture showing the
 * authoring model: it is NOT executed by the local Python runtime,
 * which runs the equivalent restricted step-plan instead (see
 * README.md "What the local runtime does and does not do").
 */
export async function onExecutePostLogin(event, api) {
  const tier = event.secrets["tier-api-key"] ? "enterprise" : "standard";
  api.idToken.setCustomClaim("https://acme.example/tier", tier);
  if (event.user.email_verified === false) {
    api.access.deny("Verify your email before signing in.");
  }
}
