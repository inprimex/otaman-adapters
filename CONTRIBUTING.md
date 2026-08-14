# Contributing to Otaman Adapters

Thank you for your interest in contributing to Otaman Adapters! We welcome contributions from the community and appreciate your help in making this project better.

## How to Contribute

1. **Fork the repository** on GitHub
2. **Create a feature branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** and ensure tests pass
4. **Commit with clear messages** following the project's commit style
5. **Push to your fork** and open a Pull Request

## Code Standards

- Follow the existing code style and conventions
- Write tests for new functionality
- Ensure all tests pass before submitting your PR
- Keep commits atomic and well-documented

## Testing Requirements

Before submitting a pull request:
- Run the test suite: `pytest tests/`
- Verify type hints pass: `mypy src/`
- Check for linting issues: `ruff check src/`

## Pull Request Checklist

- [ ] Tests added/updated and passing
- [ ] Code follows project style guidelines
- [ ] Documentation updated (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] CLA signed (see below)

## Contributor License Agreement

By submitting a pull request, you agree to the Contributor License Agreement (CLA).

We use a CLA to preserve the ability to dual-license contributions under both AGPL-3.0 (Community Edition) and proprietary licenses (Enterprise Edition).

**First-time contributors:** CLA Assistant will guide you through signing on your first PR:
1. Open your PR
2. CLA Assistant bot will comment with a sign link
3. Sign the CLA (takes ~2 minutes)
4. CLA Assistant marks the PR ready to merge

**What you're signing:**
- **Individual CLA (ICLA)** — grants Inprimex Lab LLC permission to use your code in both CE (open source) and EE (proprietary)

See [otaman-meta CLA templates](https://github.com/inprimex/otaman-meta/tree/main/strategy/ce-ee-prep/legal) for the full agreement text and FAQ.

## Questions or Issues?

- Open an issue for bug reports or feature requests
- See [SECURITY.md](SECURITY.md) for reporting security vulnerabilities
- For licensing questions, contact: licensing@inprimex.com

Thank you for contributing to Otaman!
