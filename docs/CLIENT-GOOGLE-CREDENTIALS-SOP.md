# Setting Up Google Access for Your Content Pipeline

> **What this is:** A step-by-step guide to create **one Google "service account"** and give it read-only access to your **Google Search Console** and **Google Analytics (GA4)**. The content pipeline uses this to find keyword opportunities and detect which pages are losing traffic.
>
> **Why a service account:** It's a dedicated, robot-style Google login that *you own and control*. Unlike a personal login, it never expires, never needs a password reset, and isn't tied to any one person leaving the team. You can revoke it any time with one click.
>
> **Time required:** About 20–30 minutes, once.
> **Cost:** Free. No credit card or billing account is required — these Google APIs are free to use.
> **You'll finish with:** One `.json` file to send back to us, plus your GA4 Property ID.

---

## Before you begin — what you need

Please confirm you have all three. If you're missing any, the person on your team who set up Search Console / Analytics has them.

- [ ] A **Google account** (the same one you normally use for Google services is fine).
- [ ] **Owner** access to the Google Search Console property for **firstmovers.ai** (you need to be able to add users in Search Console).
- [ ] **Administrator** access to your **Google Analytics 4** property (you need to be able to add users in Analytics).

> Tip: open these three tabs now so you can switch between them easily:
> 1. https://console.cloud.google.com (Google Cloud — where we create the account)
> 2. https://search.google.com/search-console (Search Console)
> 3. https://analytics.google.com (Analytics)

---

## Part 1 — Create a Google Cloud project

A "project" is just a container. We'll make one to hold the service account.

1. Go to **https://console.cloud.google.com** and sign in with your Google account.
2. At the very top of the page, click the **project dropdown** (it's next to the "Google Cloud" logo — it may say "Select a project" or show an existing project name).
3. In the window that opens, click **NEW PROJECT** (top right).
4. **Project name:** type something clear, e.g. `FirstMovers Content Pipeline`.
5. Leave "Location/Organization" as-is. Click **CREATE**.
6. Wait ~10 seconds for it to finish, then make sure this new project is **selected** in the top dropdown before continuing. (Click the dropdown again and pick it if needed.)

✅ **Done when:** the project name at the top of the screen reads `FirstMovers Content Pipeline`.

---

## Part 2 — Turn on the two Google APIs we need

We need to enable two services in this project.

### 2a. Search Console API

1. In the search bar at the top of Google Cloud, type **`Google Search Console API`** and click the matching result.
2. Click the blue **ENABLE** button.
3. Wait for it to say it's enabled.

### 2b. Analytics Data API

1. In the same top search bar, type **`Google Analytics Data API`** and click the matching result.
2. Click the blue **ENABLE** button.
3. Wait for it to say it's enabled.

✅ **Done when:** both APIs show as enabled. (If a button says "MANAGE" instead of "ENABLE", it's already on — that's fine.)

---

## Part 3 — Create the service account

1. In the top search bar, type **`Service Accounts`** and open the **Service Accounts** page (under "IAM & Admin").
2. Make sure your project (`FirstMovers Content Pipeline`) is selected at the top.
3. Click **+ CREATE SERVICE ACCOUNT** (near the top).
4. **Service account name:** type `content-pipeline`.
   - The "Service account ID" fills in automatically — leave it.
5. Click **CREATE AND CONTINUE**.
6. On the **"Grant this service account access to project"** step — you can **skip this**. Just click **CONTINUE**.
7. On the final **"Grant users access"** step — also **skip**. Click **DONE**.

You'll land back on the Service Accounts list, where you'll now see your new account.

### 📋 Copy the service account email — you'll need it twice

The new account has an **email address** that looks like:

```
content-pipeline@firstmovers-content-pipeline.iam.gserviceaccount.com
```

Click on the service account in the list and **copy that email address**. Keep it handy — you'll paste it into Search Console and Analytics in Parts 5 and 6.

✅ **Done when:** you've copied the service account's email address somewhere you can find it.

---

## Part 4 — Download the key file (the `.json`)

This is the file you'll send back to us.

1. Still on the **Service Accounts** page, click your `content-pipeline` account to open it.
2. Go to the **KEYS** tab (near the top).
3. Click **ADD KEY** → **Create new key**.
4. Choose **JSON** (it's the default), then click **CREATE**.
5. A `.json` file will **automatically download** to your computer.

> 🔒 **Treat this file like a password.** Anyone who has it can read your Search Console and Analytics data. Don't email it in plain text or post it in chat. See "How to send it to us" at the end.

✅ **Done when:** you have a file like `firstmovers-content-pipeline-xxxxxxxx.json` saved on your computer.

---

## Part 5 — Give the service account access to Search Console

Now we let the robot account *read* your Search Console.

1. Go to **https://search.google.com/search-console**.
2. In the top-left **property dropdown**, select the **firstmovers.ai** property.
3. In the left sidebar, scroll to the bottom and click **Settings** (gear icon).
4. Click **Users and permissions**.
5. Click **ADD USER** (top right).
6. **Email address:** paste the **service account email** you copied in Part 3.
7. **Permission:** choose **Full**.
   - (Full is required so the pipeline can read every report it needs. The account still can't change your site — it only has access to Search Console data.)
8. Click **ADD**.

✅ **Done when:** the `content-pipeline@...gserviceaccount.com` email appears in your Search Console users list.

---

## Part 6 — Give the service account access to Analytics (GA4)

Same idea, in Analytics.

1. Go to **https://analytics.google.com**.
2. Make sure the correct **property** is selected (top-left account/property selector). It should be the firstmovers.ai GA4 property.
3. Click **Admin** (the gear icon, bottom-left).
4. In the **Property** column, click **Property Access Management**.
5. Click the blue **+** (top right) → **Add users**.
6. **Email address:** paste the **service account email** again.
7. **Uncheck** "Notify new users by email" (the robot account has no inbox — this avoids a bounce).
8. **Role:** choose **Viewer**.
9. Click **Add** (top right).

✅ **Done when:** the service account email appears in the Property Access Management list with the **Viewer** role.

---

## Part 7 — Find your GA4 Property ID

We need one number to point the pipeline at the right Analytics property.

1. Still in Analytics, click **Admin** (bottom-left gear).
2. In the **Property** column, click **Property details** (or **Property Settings**).
3. Near the top right you'll see **PROPERTY ID** — a number like `123456789`.
4. **Copy that number.**

> Note: the Property ID is just a number (e.g. `123456789`). It is **not** the "G-XXXXXXX" measurement ID you may see elsewhere — that's a different thing.

✅ **Done when:** you've written down your numeric Property ID.

---

## Part 8 — Send it back to us (securely)

Please send us **two things**:

1. **The `.json` key file** from Part 4.
2. **Your GA4 Property ID** number from Part 7.

**How to send the `.json` file safely — pick one:**
- **Best:** a password manager share (1Password, Bitwarden) or a Google Drive link shared *only* with us.
- **Good:** a file-transfer link that expires (e.g. WeTransfer, Tresorit).
- **Please avoid:** pasting the file contents into a plain email or chat message.

The Property ID number is not sensitive — you can send that in a normal message.

---

## 🔒 Security notes (good to know)

- This service account is **read-only** for Search Console and Analytics. It **cannot** edit your website, change settings, or delete anything.
- **You stay in control.** You can revoke its access at any time by removing the email from the Search Console users list (Part 5) and the Analytics access list (Part 6), or by deleting the key in Google Cloud.
- The account **never expires** and needs no maintenance — unlike a personal login, it won't break if someone leaves the team or changes their password.
- If you ever want to rotate the key (replace it with a fresh one), just repeat Part 4 to create a new key and send it over; we'll swap it in and you can delete the old one.

---

## ❓ Troubleshooting

| Problem | What to do |
|---|---|
| I don't see an **ADD USER** button in Search Console | You're not an **Owner** of the property. Ask whoever set up Search Console to either add you as an Owner, or to do Part 5 for you using the service account email. |
| I can't find **Property Access Management** in Analytics | You need **Administrator** access on the GA4 property. Ask your Analytics admin to add you, or to do Part 6 for you. |
| The **ENABLE** button is greyed out / asks for billing | Double-check you searched for the exact API names in Part 2. These two APIs are free and should not require billing. If it still asks, let us know — don't enter card details. |
| I created the project but the APIs/service account aren't showing up | Confirm the correct project is selected in the **top dropdown**. It's easy to accidentally be in a different project. |
| There are multiple GA4 properties and I'm not sure which one | Send us the names you see in the Analytics property selector and we'll tell you which Property ID we need. |

---

## ✅ Final checklist

Before you send everything over, confirm:

- [ ] Created a Google Cloud project
- [ ] Enabled **Google Search Console API** and **Google Analytics Data API**
- [ ] Created the `content-pipeline` service account and copied its email
- [ ] Downloaded the `.json` key file
- [ ] Added the service account email to **Search Console** with **Full** access
- [ ] Added the service account email to **Analytics** with **Viewer** access
- [ ] Found your **GA4 Property ID**
- [ ] Sent us the `.json` file (securely) **and** the Property ID

That's everything — thank you! Once we receive the file and Property ID, we'll connect it on our end (about 5 minutes) and confirm both Search Console and Analytics are flowing.
