// Small Node bridge because the Python connector package is unavailable.
// Input travels through stdin; never put password links or credentials in argv.
import { ReplitConnectors } from "@replit/connectors-sdk";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const connectors = new ReplitConnectors();

async function request(path, options = {}) {
    const response = await connectors.proxy("twilio", path, options);
    if (!response.ok) {
        if ([401, 403].includes(response.status)) {
            throw new Error("Twilio rejected authentication. Update the Twilio connection credentials.");
        }
        throw new Error(`Twilio rejected the request (HTTP ${response.status}). Check the sender and recipient configuration.`);
    }
    return response.json();
}

try {
    const args = JSON.parse(input);
    const data = await request("/2010-04-01/Accounts.json");
    const accounts = (data.accounts || []).filter(a => a.status === "active");
    const account = args.accountSid
        ? accounts.find(a => a.sid === args.accountSid)
        : accounts.find(a => a.sid === a.owner_account_sid) || (accounts.length === 1 ? accounts[0] : null);
    if (!account) throw new Error("Choose an active Twilio account for coach setup SMS.");
    const phones = await request(`/2010-04-01/Accounts/${account.sid}/IncomingPhoneNumbers.json?PageSize=1000`);
    const smsPhones = (phones.incoming_phone_numbers || []).filter(p => p.capabilities?.sms || p.capabilities?.SMS);
    const sender = args.from
        ? smsPhones.find(p => p.phone_number === args.from)
        : (smsPhones.length === 1 ? smsPhones[0] : null);
    if (!sender) throw new Error("The configured sender is not an SMS-enabled number on the connected Twilio account.");
    if (args.mode === "discover") {
        process.stdout.write(JSON.stringify({ok: true, accountSid: account.sid, from: sender.phone_number}));
    } else if (args.mode === "send") {
        const body = new URLSearchParams({To: args.to, From: sender.phone_number, Body: args.message});
        const message = await request(`/2010-04-01/Accounts/${account.sid}/Messages.json`, {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: body.toString(),
        });
        if (!message.sid || ["failed", "undelivered"].includes(message.status)) {
            throw new Error("Twilio did not accept the SMS. No setup link was activated.");
        }
        process.stdout.write(JSON.stringify({ok: true, sid: message.sid}));
    } else {
        throw new Error("Unsupported SMS operation.");
    }
} catch (error) {
    // Provider response bodies can contain sensitive data. Only emit safe errors.
    const safe = error.message?.startsWith("Twilio ") ||
        error.message?.startsWith("Choose an active ") ||
        error.message?.startsWith("The configured sender ") ||
        error.message === "Unsupported SMS operation.";
    process.stdout.write(JSON.stringify({
        ok: false,
        error: safe ? error.message : "The Twilio connector is unavailable. Check the connection and try again.",
    }));
}