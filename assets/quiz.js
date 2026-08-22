/* quiz.js — reusable quiz widget.
   Usage:
     <div id="quiz-1"></div>
     <script src="../assets/quiz.js"></script>
     <script>
       LessonQuiz.render(document.getElementById('quiz-1'), {
         title: 'Map the loop',
         questions: [
           { q: 'Question text?',
             options: ['Option A', 'Option B', 'Option C', 'Option D'],
             answer: 0,
             explain: 'Why the answer is A.' },
           ...
         ]
       });
     </script>
   Authoring rule: make all four options the same number of words
   (and the same character count where possible) so nothing gives the answer away.
*/
(function (global) {
  'use strict';

  function render(container, cfg) {
    var score = 0;
    var answered = 0;
    var total = cfg.questions.length;

    var root = document.createElement('div');
    root.className = 'quiz';

    var scoreEl = document.createElement('div');
    scoreEl.className = 'quiz-score no-print';

    if (cfg.title) {
      var title = document.createElement('h4');
      title.textContent = cfg.title;
      root.appendChild(title);
    }

    updateScore();

    cfg.questions.forEach(function (q, qi) {
      var qEl = document.createElement('div');
      qEl.className = 'quiz-q';

      var qtext = document.createElement('div');
      qtext.className = 'qtext';
      qtext.textContent = (qi + 1) + '. ' + q.q;
      qEl.appendChild(qtext);

      var explainEl = document.createElement('div');
      explainEl.className = 'explain';
      explainEl.innerHTML = '<b>Answer:</b> ' + q.explain;
      qEl.appendChild(explainEl);

      q.options.forEach(function (optText, oi) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'opt';
        btn.textContent = optText;
        btn.addEventListener('click', function () {
          if (btn.disabled) return;
          answered++;
          var isCorrect = (oi === q.answer);
          if (isCorrect) {
            score++;
            btn.classList.add('correct');
          } else {
            btn.classList.add('wrong');
            qEl.querySelectorAll('.opt')[q.answer].classList.add('correct');
          }
          qEl.querySelectorAll('.opt').forEach(function (b) { b.disabled = true; });
          explainEl.classList.add('show');
          updateScore();
        });
        qEl.appendChild(btn);
      });

      root.appendChild(qEl);
    });

    function updateScore() {
      scoreEl.textContent = 'Score: ' + score + ' / ' + answered +
        (answered === total && total > 0 ? '  —  done!' : '');
    }

    root.appendChild(scoreEl);
    container.appendChild(root);
  }

  global.LessonQuiz = { render: render };
})(window);
