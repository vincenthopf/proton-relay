func askPass(prompt string) ([]byte, error) {
	// Check for environment variable first
	if prompt == "Password" || prompt == "Mailbox password" {
		if v := os.Getenv("HYDROXIDE_AUTH_PASS"); v != "" {
			return []byte(v), nil
		}
	}
	
	f := os.Stdin
	if !term.IsTerminal(int(f.Fd())) {
		// Try to read from stdin if piped
		scanner := bufio.NewScanner(os.Stdin)
		if scanner.Scan() {
			return []byte(scanner.Text()), nil
		}
		// Fallback to /dev/tty  
		var err error
		if f, err = os.Open("/dev/tty"); err != nil {
			// If no tty and env var not set, return error
			return nil, err
		}
		defer f.Close()
	}
	fmt.Fprintf(os.Stderr, "%v: ", prompt)
	b, err := term.ReadPassword(int(f.Fd()))
	if err == nil {
		fmt.Fprintf(os.Stderr, "\n")
	}
	return b, err
}