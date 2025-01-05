.PHONY: pdf2png
pdf2png:
	convert -density 300 ./assets/pmr446-listen-all.pdf ./assets/pmr446-listen-all.png
	convert -density 300 ./assets/pmr446-select-channel.pdf ./assets/pmr446-select-channel.png

