# Genetic Programming for Autonomous ML Research — Resources

## Knowledge

- [Book (free PDF): _A Field Guide to Genetic Programming_ by Poli, Langdon & McPhee (2008)](http://www.gp-field-guide.org.uk/)
  The standard free primer on GP, Creative Commons licensed. Chapter 1 ("Genetic Programming in a Nutshell") is the primary reading for Lesson 1. Use for: the canonical GP loop, program trees, mutation/crossover, selection schemes, GP vs other methods.

- [Book: _Genetic Programming: On the Programming of Computers by Means of Natural Selection_ by John Koza (MIT Press, 1992)](https://mitpress.mit.edu/9780262111706/genetic-programming/)
  The founding text of GP (Lisp program trees as individuals). Use for: history, the original statement of the loop, why GP = "programs evolve, not numbers."

- [Paper: _Mathematical discoveries from program search with large language models_ (Romera-Paredes et al., Nature 625, 2024) — FunSearch](https://pmc.ncbi.nlm.nih.gov/articles/PMC10794145/)
  Open-access version. The cleanest published example of "LLM proposes programs, an evaluator scores them, evolution selects" — cap-set and bin-packing discoveries. Use for: the direct bridge between GP and LLM-driven autoresearch. (DOI: 10.1038/s41586-023-06924-6)

- [Paper: _Evolution Strategies as a Scalable Alternative to Reinforcement Learning_ (Salimans et al., 2017)](https://arxiv.org/abs/1703.03864)
  OpenAI's ES paper: gradient-free training of deep RL policies by perturbing the whole weight vector. Use for: understanding (1+1)-ES / population-vs-perturbations, why "hill climbing on a huge vector" scales, and the formal name for autoresearch's loop.

- [Paper: _Regularized Evolution for Image Classifier Architecture Search_ (Real et al., AAAI 2019)](https://arxiv.org/abs/1802.01548)
  AmoebaNet: evolutionary NAS that beat human-designed networks. Use for: tournament selection, the age/regularized-evolution trick (prefer younger genotypes), evolutionary search with expensive fitness (short training runs).

- [Paper/Project: _Evolving Neural Networks through Augmenting Topologies_ — NEAT (Stanley & Miikkulainen, Evol. Comp. 10(2), 2002)](https://nn.cs.utexas.edu/?neat)
  Neuroevolution of topology *and* weights; speciation, innovation numbers, complexification. Use for: evolution when the individual is a network graph, and how to make crossover work on variable-length structures.

- [Repo: `karpathy/autoresearch` — AI agents running research on single-GPU nanochat training automatically](https://github.com/karpathy/autoresearch)
  The mission artifact. Read the [README](https://github.com/karpathy/autoresearch) and, above all, the [raw `program.md`](https://raw.githubusercontent.com/karpathy/autoresearch/master/program.md) — the actual "research org code" that runs the agent. Use for: grounding every lesson in the real loop (5-min budget, `val_bpb`, keep/discard via git).

- [Repo: `karpathy/nanochat` — the training setup autoresearch experiments on](https://github.com/karpathy/nanochat)
  Parent project: single-GPU LLM training. Use for: understanding what `train.py` contains, `val_bpb`, BPE tokenizer, Muon/AdamW, the fixed-budget design choice.

- [Blog: Karpathy, _Software 2.0_ (2017)](https://karpathy.medium.com/software-2-0-a64152b37c35)
  The essay that frames neural nets as "programs we write by optimization rather than by hand" — the cultural backdrop for why "evolving the code that trains the model" is a natural next step. Use for: motivation and framing.

## Wisdom (Communities)

- [ACM SIGEVO — the evolutionary computation special interest group](https://sigevo.org/)
  The real community: runs GECCO (the main GP/EC conference), publishes SIGEVOlution. Use for: finding practitioners, papers, events when you want to test ideas against experts.

- [r/evolutionarycomputation on Reddit](https://www.reddit.com/r/evolutionarycomputation/)
  Active discussion of GP/EC practice, libraries, and papers. Use for: quick community feedback, implementation questions (e.g., DEAP, evosax).

- [Genetic Programming and Evolvable Machines (GPEM) journal](https://link.springer.com/journal/10710)
  Peer-reviewed GP outlet. Use for: state-of-the-art surveys and "human-competitive results produced by GP" retrospectives.

## Gaps
- **Deep Neuroevolution** (Such et al., 2017 — GAs as a competitive alternative for deep RL at scale): authors/title/venue known, but the arXiv link could not be verified during setup (API rate limits). Verify before citing.
- **A recent survey of evolutionary deep learning** (e.g., "evolutionary computation meets deep learning" surveys): candidate surveys exist but none verified yet. Search and verify before adding.
- Community preference: user hasn't said whether they want to join communities. Ask.
