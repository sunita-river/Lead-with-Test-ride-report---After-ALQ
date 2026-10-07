import { Page } from '@playwright/test';

export class LoginPage {
  constructor(private readonly page: Page) {}

  async login(loginUrl: string, username: string, password: string) {
    await this.page.goto(loginUrl);
    await this.page.getByRole('textbox', { name: 'Username' }).click();
    await this.page.getByRole('textbox', { name: 'Username' }).fill(username);
    await this.page.getByRole('button', { name: 'Log In to Sandbox' }).click();
    await this.page.getByRole('textbox', { name: 'Password' }).click();
    await this.page.getByRole('textbox', { name: 'Password' }).fill(password);
    await this.page.getByRole('button', { name: 'Log In to Sandbox' }).click();

    // Salesforce may show a manual identity-verification step after this.
    // Wait for the actual home page (App Launcher) so callers never treat a
    // half-completed login as done.
    await this.page.getByRole('button', { name: 'App Launcher' }).waitFor({ timeout: 180_000 });
  }
}
