# Contributing to AWS Smart Resource Right-Sizer

Thank you for your interest in contributing! We welcome bug reports, feature requests, and pull requests.

## How to Contribute

### Reporting Bugs

Open an issue on GitHub with:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- AWS region and resource types affected
- Log snippets (redact sensitive info)

### Requesting Features

Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternative approaches considered

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Ensure code follows PEP 8 style guidelines
6. Add docstrings to new functions/classes
7. Update README if needed
8. Commit your changes (`git commit -m 'Add amazing feature'`)
9. Push to your branch (`git push origin feature/amazing-feature`)
10. Open a Pull Request

## Code Style

- Follow PEP 8 for Python code
- Use type hints for function parameters and returns
- Add docstrings (Google style) to all functions and classes
- Keep functions focused and under 50 lines when possible

## Testing

Before submitting:
- Test with multiple resource types (EC2, RDS, Lambda)
- Verify dry-run mode works
- Check that alerts format correctly
- Test error handling (invalid credentials, API throttling)

## Security

If you discover a security issue, please email aws-security@amazon.com instead of opening a public issue.

## License

By contributing, you agree that your contributions will be licensed under the MIT-0 License.
