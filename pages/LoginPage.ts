import { Page } from '@playwright/test';
import { healed } from './selfHeal';

export class LoginPage {
  constructor(private readonly page: Page) {}

  async login(loginUrl: string, username: string, password: string) {
    await this.page.goto(loginUrl);
    // Each locator has backups (selfHeal.ts): used, and logged as [HEAL], only if the usual one finds nothing.
    const usernameBox = await healed(this.page, 'Username box', this.page.getByRole('textbox', { name: 'Username' }),
      [this.page.locator('#username:visible'), this.page.locator('input[name="username"]:visible'),
        this.page.getByLabel(/user ?name/i).filter({ visible: true })]);
    await usernameBox.click();
    await usernameBox.fill(username);
    await (await this.logInButton()).click();
    const passwordBox = await healed(this.page, 'Password box', this.page.getByRole('textbox', { name: 'Password' }),
      [this.page.locator('#password:visible'), this.page.locator('input[name="pw"]:visible'),
        this.page.getByLabel(/password/i).filter({ visible: true })]);
    await passwordBox.click();
    await passwordBox.fill(password);
    await (await this.logInButton()).click();

    // Salesforce may show a manual identity-verification step after this.
    // Wait for the actual home page (App Launcher) so callers never treat a
    // half-completed login as done.
    const appLauncher = await healed(this.page, 'App Launcher button', this.page.getByRole('button', { name: 'App Launcher' }),
      [this.page.locator('button[title="App Launcher"]:visible'),
        this.page.locator('.slds-icon-waffle_container:visible').first()], 180_000);
    await appLauncher.waitFor({ timeout: 180_000 });
  }

  private logInButton() {
    return healed(this.page, 'Log In button', this.page.getByRole('button', { name: 'Log In to Sandbox' }),
      [this.page.locator('#Login:visible'), this.page.locator('input[name="Login"]:visible'),
        this.page.getByRole('button', { name: /^log in/i })]);
  }
}
